from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import httpx
import json
import asyncio
import numpy as np
from datetime import datetime
from typing import List
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from indicators import (
    compute_adx, compute_rsi, compute_bollinger_bands,
    compute_momentum_12_1, compute_volume_ratio,
)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def safe(val):
    if val is None:
        return None
    if isinstance(val, float) and pd.isna(val):
        return None
    return val


@app.get("/api/stock/{ticker}")
def get_stock(ticker: str):
    ticker = ticker.upper()
    t = yf.Ticker(ticker)
    info = t.info

    if not info or info.get("regularMarketPrice") is None and info.get("currentPrice") is None:
        raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' not found")

    hist = t.history(period="1y")
    hist = hist[hist["Close"].notna()]
    if hist.empty:
        raise HTTPException(status_code=404, detail="No price history available")

    close = hist["Close"]

    # Indicators
    hist.ta.rsi(length=14, append=True)
    hist.ta.macd(append=True)
    hist.ta.vwap(append=True)

    rsi_val    = safe(hist["RSI_14"].iloc[-1])        if "RSI_14"      in hist.columns else None
    macd_val   = safe(hist["MACD_12_26_9"].iloc[-1])  if "MACD_12_26_9"  in hist.columns else None
    signal_val = safe(hist["MACDs_12_26_9"].iloc[-1]) if "MACDs_12_26_9" in hist.columns else None
    vwap_cols  = [c for c in hist.columns if c.startswith("VWAP")]
    vwap_val   = safe(hist[vwap_cols[0]].iloc[-1]) if vwap_cols else None

    ma50  = float(close.rolling(50).mean().iloc[-1])
    ma200 = float(close.rolling(200).mean().iloc[-1])

    # Real-time price and 1D change from the info dict — hist["Close"] lags by one
    # session during market hours because today's candle has no official close yet.
    price_now = float(info.get("currentPrice") or info.get("regularMarketPrice") or close.iloc[-1])
    _prev     = info.get("previousClose") or info.get("regularMarketPreviousClose")
    change_1d = round((price_now / float(_prev) - 1) * 100, 2) if _prev else 0.0

    vol_today = int(hist["Volume"].iloc[-1])
    vol_avg20 = float(hist["Volume"].rolling(20).mean().iloc[-1])

    # 1-year price chart data (weekly sampled for performance)
    chart_data = []
    hist_reset = hist.reset_index()
    for _, row in hist_reset.iloc[::3].iterrows():
        chart_data.append({
            "date": row["Date"].strftime("%Y-%m-%d"),
            "close": round(float(row["Close"]), 2),
            "volume": int(row["Volume"]),
        })

    roe           = safe(info.get("returnOnEquity"))
    # Gross margin is meaningless (returns 0.0) for banks/financials — treat as N/A
    gross_margin_raw = safe(info.get("grossMargins"))
    gross_margin  = gross_margin_raw if (gross_margin_raw and gross_margin_raw > 0.001) else None

    # Compute TTM operating margin from last 4 quarters (more accurate than info field which can be single-quarter)
    op_margin = None
    try:
        inc_q = t.quarterly_income_stmt
        if "Total Revenue" in inc_q.index and "Operating Income" in inc_q.index:
            rev_ttm = float(inc_q.loc["Total Revenue"].iloc[:4].dropna().sum())
            op_ttm  = float(inc_q.loc["Operating Income"].iloc[:4].dropna().sum())
            if rev_ttm > 0:
                op_margin = op_ttm / rev_ttm
    except Exception:
        pass
    if op_margin is None:
        op_margin = safe(info.get("operatingMargins"))

    net_margin    = safe(info.get("profitMargins"))
    rev_growth    = safe(info.get("revenueGrowth"))
    eps_growth    = safe(info.get("earningsGrowth"))

    # Compute TTM FCF by summing last 4 quarters (annual cashflow misses the most recent quarter)
    free_cf = None
    try:
        cf_q = t.quarterly_cashflow
        if "Free Cash Flow" in cf_q.index:
            last4 = cf_q.loc["Free Cash Flow"].iloc[:4].dropna()
            if len(last4) >= 3:
                free_cf = float(last4.sum())
    except Exception:
        pass
    if free_cf is None:
        try:
            cf_stmt = t.cashflow
            if "Free Cash Flow" in cf_stmt.index:
                _v = cf_stmt.loc["Free Cash Flow"].iloc[0]
                if not pd.isna(_v):
                    free_cf = float(_v)
        except Exception:
            free_cf = safe(info.get("freeCashflow"))

    debt_eq       = safe(info.get("debtToEquity"))
    total_cash    = safe(info.get("totalCash"))
    total_debt    = safe(info.get("totalDebt"))
    total_rev     = safe(info.get("totalRevenue"))

    # Dividend yield: yfinance's dividendYield field is already in % form for some tickers
    # and returns None for others even when dividends are paid (e.g. JNJ, JPM).
    # Most reliable approach: calculate from annual dividend rate / price.
    # Fall back to trailingAnnualDividendRate if forward dividendRate is missing.
    div_rate = safe(info.get("dividendRate")) or safe(info.get("trailingAnnualDividendRate"))
    div_yield = round((div_rate / price_now) * 100, 2) if (div_rate and div_rate > 0 and price_now) else None

    pre_price  = safe(info.get("preMarketPrice"))
    pre_pct    = safe(info.get("preMarketChangePercent"))
    post_price = safe(info.get("postMarketPrice"))
    post_pct   = safe(info.get("postMarketChangePercent"))

    return {
        "ticker": ticker,
        "name": info.get("longName", ticker),
        "sector": info.get("sector", ""),
        "industry": info.get("industry", ""),
        "price": round(price_now, 2),
        "change": change_1d,
        "preMarket":  { "price": round(pre_price,  2) if pre_price  else None, "changePct": round(pre_pct,  3) if pre_pct  else None },
        "postMarket": { "price": round(post_price, 2) if post_price else None, "changePct": round(post_pct, 3) if post_pct else None },
        "marketCap": safe(info.get("marketCap")),
        "fiftyTwoWeekHigh": safe(info.get("fiftyTwoWeekHigh")),
        "fiftyTwoWeekLow":  safe(info.get("fiftyTwoWeekLow")),
        "beta": round(safe(info.get("beta")) or 0, 2) or None,
        "eps":  safe(info.get("trailingEps")),
        "revenueB": round(total_rev / 1e9, 2) if total_rev else None,
        "valuation": {
            "peTrailing":  round(safe(info.get("trailingPE")) or 0, 2) or None,
            "evEbitda":    round(safe(info.get("enterpriseToEbitda")) or 0, 2) or None,
            "evRevenue":   round(safe(info.get("enterpriseToRevenue")) or 0, 2) or None,
            "priceToBook": round(safe(info.get("priceToBook")) or 0, 2) or None,
        },
        "profitability": {
            "roe":              round(roe * 100, 2)          if roe          else None,
            "grossMargin":      round(gross_margin * 100, 2) if gross_margin else None,
            "operatingMargin":  round(op_margin * 100, 2)    if op_margin    else None,
            "netMargin":        round(net_margin * 100, 2)   if net_margin   else None,
            "revenueGrowth":    round(rev_growth * 100, 2)   if rev_growth   else None,
            "epsGrowth":        round(eps_growth * 100, 2)   if eps_growth   else None,
        },
        "balanceSheet": {
            "debtEquity":    round(debt_eq, 2) if debt_eq else None,
            "freeCashFlow":  round(free_cf / 1e9, 2) if free_cf else None,
            "totalCash":     round(total_cash / 1e9, 2) if total_cash else None,
            "totalDebt":     round(total_debt / 1e9, 2) if total_debt else None,
            "dividendYield": div_yield,
        },
        "technicals": {
            "rsi":         round(rsi_val, 2)    if rsi_val    else None,
            "macd":        round(macd_val, 2)   if macd_val   else None,
            "macdSignal":  round(signal_val, 2) if signal_val else None,
            "vwap":        round(vwap_val, 2)   if vwap_val   else None,
            "ma50":        round(ma50, 2),
            "ma200":       round(ma200, 2),
            "volume":      vol_today,
            "volumeAvg20": round(vol_avg20),
        },
        "chart": chart_data,
    }


@app.get("/api/stock/{ticker}/financials")
def get_financials(ticker: str):
    ticker = ticker.upper()
    t = yf.Ticker(ticker)
    info = t.info
    if not info or (info.get("regularMarketPrice") is None and info.get("currentPrice") is None):
        raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' not found")

    # ── Annual Revenue (last 4 fiscal years, oldest → newest) ────────────────
    revenue = []
    try:
        inc = t.income_stmt
        if "Total Revenue" in inc.index:
            rows = [(col, inc.loc["Total Revenue", col]) for col in inc.columns[:4]]
            rows.reverse()
            for col, val in rows:
                if not pd.isna(val):
                    revenue.append({"year": str(col.year), "value": round(float(val) / 1e9, 2)})
    except Exception:
        pass

    # ── Annual Free Cash Flow (last 4 fiscal years, oldest → newest) ─────────
    fcf = []
    try:
        cf = t.cashflow
        if "Free Cash Flow" in cf.index:
            rows = [(col, cf.loc["Free Cash Flow", col]) for col in cf.columns[:4]]
            rows.reverse()
            for col, val in rows:
                if not pd.isna(val):
                    fcf.append({"year": str(col.year), "value": round(float(val) / 1e9, 2)})
    except Exception:
        pass

    # ── Annual P/E history (last 4 fiscal years + current TTM) ──────────────
    # Use annual EPS from income statement + stock price at fiscal year-end date
    pe_history = []
    try:
        inc = t.income_stmt
        eps_key = next((k for k in ["Diluted EPS", "Basic EPS"] if k in inc.index), None)
        if eps_key:
            price_hist = t.history(period="5y", interval="1d")
            price_hist = price_hist[price_hist["Close"].notna()]
            if price_hist.index.tz is not None:
                price_hist.index = price_hist.index.tz_localize(None)

            annual = []
            for col in inc.columns[:4]:
                eps = inc.loc[eps_key, col]
                if pd.isna(eps) or float(eps) <= 0:
                    continue
                year_end = col.tz_localize(None) if hasattr(col, "tzinfo") and col.tzinfo else col
                # Find the nearest trading day price within 7 days of fiscal year end
                window = price_hist[abs(price_hist.index - year_end) <= pd.Timedelta(days=7)]
                if window.empty:
                    window = price_hist[abs(price_hist.index - year_end) <= pd.Timedelta(days=30)]
                if not window.empty:
                    price_at_ye = float(window["Close"].iloc[-1])
                    pe = round(price_at_ye / float(eps), 1)
                    annual.append({"year": str(col.year), "pe": pe})
            annual.reverse()  # oldest → newest
            pe_history = annual

        # Append current trailing PE
        trailing_pe = safe(info.get("trailingPE"))
        if trailing_pe:
            pe_history.append({"year": "TTM", "pe": round(float(trailing_pe), 1)})
    except Exception:
        pass

    return {"ticker": ticker, "revenue": revenue, "fcf": fcf, "peHistory": pe_history}


@app.get("/api/stock/{ticker}/chart")
def get_chart(ticker: str, period: str = "1y", interval: str = "1d"):
    import pytz
    ticker = ticker.upper()
    t      = yf.Ticker(ticker)
    et     = pytz.timezone("America/New_York")
    intraday = interval in ("1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h")

    # For 1D use 5d so we always get the last trading day even on weekends
    fetch_period = "5d" if period == "1d" else period
    hist = t.history(period=fetch_period, interval=interval, prepost=intraday)
    if hist.empty:
        raise HTTPException(status_code=404, detail="No chart data available")

    # Filter 1D to only the last trading day
    if period == "1d" and intraday:
        hist.index = hist.index.tz_convert(et)
        last_date  = hist.index.normalize().unique()[-1]
        hist       = hist[hist.index.normalize() == last_date]

    hist_reset = hist.reset_index()
    dt_col     = "Datetime" if "Datetime" in hist_reset.columns else "Date"
    data = []
    for _, row in hist_reset.iterrows():
        dt = row[dt_col]
        if intraday:
            time_val = int(dt.timestamp())
            dt_et    = dt.astimezone(et)
            t_mins   = dt_et.hour * 60 + dt_et.minute
            if t_mins < 9 * 60 + 30:
                session = "pre"
            elif t_mins >= 16 * 60:
                session = "post"
            else:
                session = "regular"
        else:
            time_val = dt.strftime("%Y-%m-%d")
            session  = "regular"

        data.append({
            "time":    time_val,
            "open":    round(float(row["Open"]),  2),
            "high":    round(float(row["High"]),  2),
            "low":     round(float(row["Low"]),   2),
            "close":   round(float(row["Close"]), 2),
            "volume":  int(row["Volume"]),
            "session": session,
        })

    seen = {}
    for d in data:
        seen[d["time"]] = d
    data = list(seen.values())

    # Always return prevClose for the dotted reference line on the chart
    info       = t.info
    prev_close = safe(info.get("previousClose")) or safe(info.get("regularMarketPreviousClose"))

    return {"data": data, "prevClose": prev_close}


@app.get("/api/stock/{ticker}/report")
def get_stock_report(ticker: str):
    ticker = ticker.upper()
    t = yf.Ticker(ticker)
    info = t.info

    if not info or (info.get("regularMarketPrice") is None and info.get("currentPrice") is None):
        raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' not found")

    hist = t.history(period="1y")
    hist = hist[hist["Close"].notna()]
    if hist.empty:
        raise HTTPException(status_code=404, detail="No price history available")

    close = hist["Close"]
    hist.ta.rsi(length=14, append=True)
    hist.ta.macd(append=True)
    hist.ta.vwap(append=True)

    rsi_val    = safe(hist["RSI_14"].iloc[-1])        if "RSI_14"       in hist.columns else None
    macd_val   = safe(hist["MACD_12_26_9"].iloc[-1])  if "MACD_12_26_9"  in hist.columns else None
    signal_val = safe(hist["MACDs_12_26_9"].iloc[-1]) if "MACDs_12_26_9" in hist.columns else None
    vwap_cols  = [c for c in hist.columns if c.startswith("VWAP")]
    vwap_val   = safe(hist[vwap_cols[0]].iloc[-1]) if vwap_cols else None

    ma50  = float(close.rolling(50).mean().iloc[-1])
    ma200 = float(close.rolling(200).mean().iloc[-1])
    price_now = float(info.get("currentPrice") or info.get("regularMarketPrice") or close.iloc[-1])
    _prev     = info.get("previousClose") or info.get("regularMarketPreviousClose")
    change    = round((price_now / float(_prev) - 1) * 100, 2) if _prev else 0.0

    vol_today = int(hist["Volume"].iloc[-1])
    vol_avg20 = float(hist["Volume"].rolling(20).mean().iloc[-1])
    vol_ratio = round(vol_today / vol_avg20, 2) if vol_avg20 else None

    roe          = safe(info.get("returnOnEquity"))
    gross_margin = safe(info.get("grossMargins"))
    op_margin = None
    try:
        inc_q = t.quarterly_income_stmt
        if "Total Revenue" in inc_q.index and "Operating Income" in inc_q.index:
            rev_ttm = float(inc_q.loc["Total Revenue"].iloc[:4].dropna().sum())
            op_ttm  = float(inc_q.loc["Operating Income"].iloc[:4].dropna().sum())
            if rev_ttm > 0:
                op_margin = op_ttm / rev_ttm
    except Exception:
        pass
    if op_margin is None:
        op_margin = safe(info.get("operatingMargins"))
    net_margin   = safe(info.get("profitMargins"))
    rev_growth   = safe(info.get("revenueGrowth"))
    eps_growth   = safe(info.get("earningsGrowth"))
    free_cf = None
    try:
        cf_q = t.quarterly_cashflow
        if "Free Cash Flow" in cf_q.index:
            last4 = cf_q.loc["Free Cash Flow"].iloc[:4].dropna()
            if len(last4) >= 3:
                free_cf = float(last4.sum())
    except Exception:
        pass
    if free_cf is None:
        free_cf = safe(info.get("freeCashflow"))
    debt_eq      = safe(info.get("debtToEquity"))
    pe_trailing  = safe(info.get("trailingPE"))
    pe_forward   = safe(info.get("forwardPE"))
    ev_ebitda    = safe(info.get("enterpriseToEbitda"))
    market_cap   = safe(info.get("marketCap"))

    def pct(v): return f"{round(v * 100, 2)}%" if v is not None else "N/A"
    def num(v, d=2): return f"{round(v, d)}" if v is not None else "N/A"

    prompt = f"""You are a professional equity research analyst. Analyze the following data for {ticker} ({info.get('longName', ticker)}) and write a concise but thorough investment research report.

**Company:** {info.get('longName', ticker)}
**Sector:** {info.get('sector', 'N/A')} | **Industry:** {info.get('industry', 'N/A')}
**Market Cap:** {'${:,.0f}B'.format(market_cap / 1e9) if market_cap else 'N/A'}

**Price & Performance**
- Current Price: ${round(price_now, 2)}
- Daily Change: {change}%
- vs 50-Day MA: {'above' if price_now > ma50 else 'below'} (MA50: ${round(ma50, 2)})
- vs 200-Day MA: {'above' if price_now > ma200 else 'below'} (MA200: ${round(ma200, 2)})

**Valuation**
- P/E (Trailing): {num(pe_trailing)}
- P/E (Forward): {num(pe_forward)}
- EV/EBITDA: {num(ev_ebitda)}

**Profitability**
- Gross Margin: {pct(gross_margin)}
- Operating Margin: {pct(op_margin)}
- Net Margin: {pct(net_margin)}
- ROE: {pct(roe)}
- Revenue Growth (YoY): {pct(rev_growth)}
- EPS Growth (YoY): {pct(eps_growth)}

**Balance Sheet**
- Debt/Equity: {num(debt_eq)}
- Free Cash Flow: {'${:.2f}B'.format(free_cf / 1e9) if free_cf else 'N/A'}

**Technical Indicators**
- RSI (14): {num(rsi_val)} ({'Overbought' if rsi_val and rsi_val > 70 else 'Oversold' if rsi_val and rsi_val < 30 else 'Neutral'})
- MACD: {num(macd_val)} | Signal: {num(signal_val)} ({'Bullish crossover' if macd_val and signal_val and macd_val > signal_val else 'Bearish crossover'})
- VWAP: {'${:.2f} (price is {} VWAP)'.format(vwap_val, 'above' if price_now > vwap_val else 'below') if vwap_val else 'N/A'}
- Volume: {'{:.1f}M'.format(vol_today / 1e6)} ({f'{vol_ratio}x avg' if vol_ratio else 'N/A'})

Write a structured report with these sections:
1. **Executive Summary** (2-3 sentences with overall take)
2. **Business Overview** (brief company description)
3. **Valuation Analysis** (assess if cheap/fair/expensive vs sector/history)
4. **Profitability & Growth** (quality of earnings and growth trajectory)
5. **Technical Picture** (momentum, trend, key levels)
6. **Key Risks** (bullet list of 3-4 main risks)
7. **Investment Conclusion** (Bullish / Neutral / Bearish with reasoning)

Be direct and opinionated. Use markdown formatting. Keep total length to ~500 words."""

    def stream_report():
        with httpx.stream(
            "POST",
            "http://localhost:11434/api/chat",
            json={
                "model": "llama3.2",
                "messages": [{"role": "user", "content": prompt}],
                "stream": True,
            },
            timeout=120,
        ) as resp:
            if resp.status_code != 200:
                yield f"data: {json.dumps({'text': 'Ollama error: ' + str(resp.status_code)})}\n\n"
                return
            for line in resp.iter_lines():
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                    text = chunk.get("message", {}).get("content", "")
                    if text:
                        yield f"data: {json.dumps({'text': text})}\n\n"
                    if chunk.get("done"):
                        break
                except Exception:
                    continue
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream_report(), media_type="text/event-stream")


@app.get("/api/stock/{ticker}/news")
def get_news(ticker: str):
    ticker = ticker.upper()
    t = yf.Ticker(ticker)
    raw = t.news or []
    items = []
    for n in raw[:20]:
        if "content" in n:
            c = n["content"]
            provider = c.get("provider", {})
            canonical = c.get("canonicalUrl", {})
            thumb = c.get("thumbnail", {})
            items.append({
                "title":       c.get("title", ""),
                "publisher":   provider.get("displayName", "") if isinstance(provider, dict) else "",
                "link":        canonical.get("url", "")        if isinstance(canonical, dict) else "",
                "publishedAt": c.get("pubDate", ""),
                "summary":     c.get("summary", ""),
                "thumbnail":   thumb.get("originalUrl", "")    if isinstance(thumb, dict) else "",
            })
        else:
            thumb = n.get("thumbnail", {})
            res   = thumb.get("resolutions", []) if isinstance(thumb, dict) else []
            items.append({
                "title":       n.get("title", ""),
                "publisher":   n.get("publisher", ""),
                "link":        n.get("link", ""),
                "publishedAt": n.get("providerPublishTime", 0),
                "summary":     "",
                "thumbnail":   res[0].get("url", "") if res else "",
            })
    items = [i for i in items if i["title"]]
    return {"ticker": ticker, "news": items}


@app.get("/api/stock/{ticker}/bull-bear")
def get_bull_bear(ticker: str):
    ticker = ticker.upper()
    t = yf.Ticker(ticker)
    info = t.info

    if not info or (info.get("regularMarketPrice") is None and info.get("currentPrice") is None):
        raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' not found")

    hist      = t.history(period="1y")
    hist      = hist[hist["Close"].notna()]
    close     = hist["Close"]
    ma50      = float(close.rolling(50).mean().iloc[-1])
    ma200     = float(close.rolling(200).mean().iloc[-1])
    price_now = float(info.get("currentPrice") or info.get("regularMarketPrice") or close.iloc[-1])

    def pct(v): return f"{round(v * 100, 2)}%" if v is not None else "N/A"
    def num(v, d=2): return f"{round(v, d)}" if v is not None else "N/A"

    pe_trailing  = safe(info.get("trailingPE"))
    pe_forward   = safe(info.get("forwardPE"))
    ev_ebitda    = safe(info.get("enterpriseToEbitda"))
    roe          = safe(info.get("returnOnEquity"))
    gross_margin = safe(info.get("grossMargins"))
    op_margin    = safe(info.get("operatingMargins"))
    net_margin   = safe(info.get("profitMargins"))
    rev_growth   = safe(info.get("revenueGrowth"))
    eps_growth   = safe(info.get("earningsGrowth"))
    free_cf      = safe(info.get("freeCashflow"))
    debt_eq      = safe(info.get("debtToEquity"))
    market_cap   = safe(info.get("marketCap"))

    prompt = f"""You are a Wall Street research analyst. Based on the data below for {ticker} ({info.get('longName', ticker)}), write a structured bull vs bear analysis.

{ticker} — {info.get('longName', ticker)}
Sector: {info.get('sector', 'N/A')} | Industry: {info.get('industry', 'N/A')}
Market Cap: {'${:,.0f}B'.format(market_cap / 1e9) if market_cap else 'N/A'}
Price: ${round(price_now, 2)} | P/E: {num(pe_trailing)} | Fwd P/E: {num(pe_forward)} | EV/EBITDA: {num(ev_ebitda)}
Margins: Gross {pct(gross_margin)}, Operating {pct(op_margin)}, Net {pct(net_margin)}
Growth: Revenue {pct(rev_growth)}, EPS {pct(eps_growth)} | ROE: {pct(roe)}
Balance Sheet: D/E {num(debt_eq)}, FCF {'${:.2f}B'.format(free_cf/1e9) if free_cf else 'N/A'}
Trend: {'above' if price_now > ma50 else 'below'} 50-DMA, {'above' if price_now > ma200 else 'below'} 200-DMA

Format your response EXACTLY as shown — use these exact headers, no intro or outro:

## BULL CASE
- [compelling argument 1 with specific numbers]
- [compelling argument 2 with specific numbers]
- [compelling argument 3 with specific numbers]
- [compelling argument 4 with specific numbers]

## BEAR CASE
- [genuine risk 1 with specific numbers]
- [genuine risk 2 with specific numbers]
- [genuine risk 3 with specific numbers]
- [genuine risk 4 with specific numbers]"""

    def stream_bb():
        with httpx.stream(
            "POST", "http://localhost:11434/api/chat",
            json={"model": "llama3.2", "messages": [{"role": "user", "content": prompt}], "stream": True},
            timeout=120,
        ) as resp:
            if resp.status_code != 200:
                yield f"data: {json.dumps({'text': 'Ollama error'})}\n\n"; return
            for line in resp.iter_lines():
                if not line: continue
                try:
                    chunk = json.loads(line)
                    text = chunk.get("message", {}).get("content", "")
                    if text: yield f"data: {json.dumps({'text': text})}\n\n"
                    if chunk.get("done"): break
                except Exception: continue
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream_bb(), media_type="text/event-stream")


class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[ChatMessage]


@app.post("/api/stock/{ticker}/chat")
def chat_stock(ticker: str, body: ChatRequest):
    ticker = ticker.upper()
    t = yf.Ticker(ticker)
    info = t.info

    if not info or (info.get("regularMarketPrice") is None and info.get("currentPrice") is None):
        raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' not found")

    hist = t.history(period="1y")
    hist = hist[hist["Close"].notna()]
    close = hist["Close"]
    hist.ta.rsi(length=14, append=True)
    hist.ta.macd(append=True)

    rsi_val    = safe(hist["RSI_14"].iloc[-1])        if "RSI_14"       in hist.columns else None
    macd_val   = safe(hist["MACD_12_26_9"].iloc[-1])  if "MACD_12_26_9"  in hist.columns else None
    signal_val = safe(hist["MACDs_12_26_9"].iloc[-1]) if "MACDs_12_26_9" in hist.columns else None
    ma50       = float(close.rolling(50).mean().iloc[-1])
    ma200      = float(close.rolling(200).mean().iloc[-1])
    price_now  = float(info.get("currentPrice") or info.get("regularMarketPrice") or close.iloc[-1])

    def pct(v): return f"{round(v * 100, 2)}%" if v is not None else "N/A"
    def num(v, d=2): return f"{round(v, d)}" if v is not None else "N/A"

    roe          = safe(info.get("returnOnEquity"))
    gross_margin = safe(info.get("grossMargins"))
    op_margin    = safe(info.get("operatingMargins"))
    net_margin   = safe(info.get("profitMargins"))
    rev_growth   = safe(info.get("revenueGrowth"))
    eps_growth   = safe(info.get("earningsGrowth"))
    free_cf      = safe(info.get("freeCashflow"))
    debt_eq      = safe(info.get("debtToEquity"))
    pe_trailing  = safe(info.get("trailingPE"))
    pe_forward   = safe(info.get("forwardPE"))
    ev_ebitda    = safe(info.get("enterpriseToEbitda"))
    market_cap   = safe(info.get("marketCap"))

    system_prompt = f"""You are a friendly stock research assistant helping everyday investors understand {ticker} ({info.get('longName', ticker)}).

LIVE DATA for {ticker}:
Price: ${round(price_now, 2)} | Market Cap: {'${:,.0f}B'.format(market_cap / 1e9) if market_cap else 'N/A'} | Sector: {info.get('sector', 'N/A')}
vs 50-DMA: {'above' if price_now > ma50 else 'below'} (${round(ma50,2)}) | vs 200-DMA: {'above' if price_now > ma200 else 'below'} (${round(ma200,2)})
P/E: {num(pe_trailing)} trailing / {num(pe_forward)} forward | EV/EBITDA: {num(ev_ebitda)}
Margins: Gross {pct(gross_margin)} | Op {pct(op_margin)} | Net {pct(net_margin)} | ROE {pct(roe)}
Growth: Revenue {pct(rev_growth)} YoY | EPS {pct(eps_growth)} YoY
Balance sheet: D/E {num(debt_eq)} | FCF {'${:.2f}B'.format(free_cf/1e9) if free_cf else 'N/A'}
Technicals: RSI {num(rsi_val)} ({'overbought' if rsi_val and rsi_val>70 else 'oversold' if rsi_val and rsi_val<30 else 'neutral'}) | MACD {'bullish' if macd_val and signal_val and macd_val>signal_val else 'bearish'}

RESPONSE RULES — follow these strictly:
1. Keep answers SHORT: 3-5 bullet points max, or 2-3 short sentences. No essays.
2. Plain English only — no jargon. If you use a term, explain it in simple words.
3. Lead with the bottom line first, then back it up with 1-2 numbers.
4. Use **bold** only for the key number or verdict. No walls of text.
5. Be direct and opinionated — say "yes", "no", "looks expensive", "good value", etc.

MANDATORY — you MUST end EVERY response with exactly this block (no exceptions, no extra text after it):

===FOLLOWUPS===
- [short follow-up question 1]?
- [short follow-up question 2]?
- [short follow-up question 3]?"""

    # Append a reminder to the last user message so the model always outputs the FOLLOWUPS block
    raw_msgs = [{"role": m.role, "content": m.content} for m in body.messages]
    if raw_msgs and raw_msgs[-1]["role"] == "user":
        raw_msgs[-1] = {
            "role": "user",
            "content": raw_msgs[-1]["content"] + "\n\n(End your reply with ===FOLLOWUPS=== and exactly 3 short follow-up questions.)",
        }
    messages = [{"role": "system", "content": system_prompt}] + raw_msgs

    def stream_chat():
        with httpx.stream(
            "POST",
            "http://localhost:11434/api/chat",
            json={"model": "llama3.2", "messages": messages, "stream": True},
            timeout=120,
        ) as resp:
            if resp.status_code != 200:
                yield f"data: {json.dumps({'text': 'Ollama error'})}\n\n"
                return
            for line in resp.iter_lines():
                if not line: continue
                try:
                    chunk = json.loads(line)
                    text = chunk.get("message", {}).get("content", "")
                    if text:
                        yield f"data: {json.dumps({'text': text})}\n\n"
                    if chunk.get("done"): break
                except Exception:
                    continue
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream_chat(), media_type="text/event-stream")


# ── Shared Ollama streaming helper ────────────────────────────────────────────
async def ollama_stream_async(prompt: str):
    """Async SSE generator — Starlette cancels this coroutine on client disconnect,
    which exits the async context manager and closes the Ollama connection immediately."""
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=10.0)
        ) as client:
            async with client.stream(
                "POST", "http://localhost:11434/api/chat",
                json={"model": "llama3.2", "messages": [{"role": "user", "content": prompt}], "stream": True},
            ) as resp:
                if resp.status_code != 200:
                    yield f"data: {json.dumps({'text': 'Ollama error'})}\n\n"
                    return
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                        text = chunk.get("message", {}).get("content", "")
                        if text:
                            yield f"data: {json.dumps({'text': text})}\n\n"
                        if chunk.get("done"):
                            break
                    except Exception:
                        continue
    except asyncio.CancelledError:
        return  # browser disconnected — Ollama connection freed immediately
    except (httpx.TimeoutException, httpx.RemoteProtocolError):
        yield f"data: {json.dumps({'text': '\n\n[Generation timed out]'})}\n\n"
    yield "data: [DONE]\n\n"


# ── equity-research: earnings-meta ────────────────────────────────────────────
@app.get("/api/stock/{ticker}/earnings-meta")
def get_earnings_meta(ticker: str):
    ticker = ticker.upper()
    t = yf.Ticker(ticker)
    info = t.info

    if not info or (info.get("regularMarketPrice") is None and info.get("currentPrice") is None):
        raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' not found")

    # Next earnings date
    next_date = None
    try:
        dates = t.earnings_dates
        if dates is not None and not dates.empty:
            now = pd.Timestamp.now(tz="UTC")
            upcoming = dates[dates.index > now]
            if not upcoming.empty:
                next_date = upcoming.index[0].strftime("%Y-%m-%d")
                # grab EPS estimate if available
    except Exception:
        pass

    # Analyst recommendations
    analyst_recs = None
    try:
        recs = t.recommendations_summary
        if recs is not None and not recs.empty:
            row = recs.iloc[0]
            analyst_recs = {
                "strongBuy":   int(row.get("strongBuy",   0)),
                "buy":         int(row.get("buy",         0)),
                "hold":        int(row.get("hold",        0)),
                "sell":        int(row.get("sell",        0)),
                "strongSell":  int(row.get("strongSell",  0)),
            }
    except Exception:
        pass

    return {
        "ticker":         ticker,
        "name":           info.get("longName", ticker),
        "nextEarnings":   next_date,
        "epsCurrentYear": safe(info.get("epsCurrentYear")),
        "epsForward":     safe(info.get("epsForward")),
        "targetMean":     safe(info.get("targetMeanPrice")),
        "targetHigh":     safe(info.get("targetHighPrice")),
        "targetLow":      safe(info.get("targetLowPrice")),
        "analystCount":   safe(info.get("numberOfAnalystOpinions")),
        "analystRecs":    analyst_recs,
        "sector":         info.get("sector", ""),
        "industry":       info.get("industry", ""),
        "price":          round(float(float(info.get("currentPrice") or info.get("regularMarketPrice") or t.history(period="1d")["Close"].dropna().iloc[-1])), 2),
    }


# ── equity-research: earnings-preview skill ───────────────────────────────────
@app.get("/api/stock/{ticker}/earnings-preview")
async def get_earnings_preview(ticker: str):
    def _build():
        t_upper = ticker.upper()
        t = yf.Ticker(t_upper)
        info = t.info
        if not info or (info.get("regularMarketPrice") is None and info.get("currentPrice") is None):
            raise HTTPException(status_code=404, detail=f"Ticker '{t_upper}' not found")

        hist      = t.history(period="1y")
        hist      = hist[hist["Close"].notna()]
        price_now = float(info.get("currentPrice") or info.get("regularMarketPrice") or hist["Close"].iloc[-1])

        next_date = None
        try:
            dates = t.earnings_dates
            if dates is not None and not dates.empty:
                upcoming = dates[dates.index > pd.Timestamp.now(tz="UTC")]
                if not upcoming.empty:
                    next_date = upcoming.index[0].strftime("%Y-%m-%d")
        except Exception:
            pass

        analyst_recs_str = "N/A"
        try:
            recs = t.recommendations_summary
            if recs is not None and not recs.empty:
                row = recs.iloc[0]
                analyst_recs_str = (f"Strong Buy: {int(row.get('strongBuy',0))}, "
                                    f"Buy: {int(row.get('buy',0))}, Hold: {int(row.get('hold',0))}, "
                                    f"Sell: {int(row.get('sell',0))}, Strong Sell: {int(row.get('strongSell',0))}")
        except Exception:
            pass

        def pct(v): return f"{round(v * 100, 2)}%" if v is not None else "N/A"
        def num(v, d=2): return f"{round(v, d)}" if v is not None else "N/A"

        target_mean = safe(info.get("targetMeanPrice"))
        upside = f"{round((target_mean / price_now - 1) * 100, 1)}%" if target_mean else "N/A"

        return f"""You are a senior equity research analyst. Generate a professional pre-earnings preview for {t_upper} ({info.get('longName', t_upper)}).

COMPANY DATA:
Company: {info.get('longName', t_upper)}
Sector: {info.get('sector', 'N/A')} | Industry: {info.get('industry', 'N/A')}
Current Price: ${round(price_now, 2)}
Next Earnings Date: {next_date or 'N/A'}

FINANCIAL METRICS:
P/E (Trailing): {num(safe(info.get('trailingPE')))} | P/E (Forward): {num(safe(info.get('forwardPE')))}
Revenue Growth (YoY): {pct(safe(info.get('revenueGrowth')))}
EPS Growth (YoY): {pct(safe(info.get('earningsGrowth')))}
Gross Margin: {pct(safe(info.get('grossMargins')))} | Operating Margin: {pct(safe(info.get('operatingMargins')))}

ANALYST CONSENSUS:
Recommendations: {analyst_recs_str}
Price Targets — Mean: ${num(target_mean)}, High: ${num(safe(info.get('targetHighPrice')))}, Low: ${num(safe(info.get('targetLowPrice')))}
Upside to Mean Target: {upside}

Write a structured earnings preview report with these exact sections:

## What to Watch
(3–4 specific metrics or themes investors will focus on in this earnings report)

## Estimates & The Bar
(Current consensus EPS/revenue estimates, whether the bar is high or low, and historical beat/miss context)

## Bull vs Bear Into Earnings
(2 reasons bulls are optimistic, 2 reasons bears are cautious — be specific with numbers)

## Key Risks to the Print
(3 specific risks that could cause a large move in either direction)

## Analyst Setup
(Summarize analyst sentiment from the recommendation data, price target spread, and conviction level)

## Trade Setup
(Likely market reaction scenarios: beat+raise vs beat+hold vs miss — what to expect for each)

Be direct and opinionated. Use markdown formatting. ~400 words."""

    prompt = await asyncio.to_thread(_build)
    return StreamingResponse(ollama_stream_async(prompt), media_type="text/event-stream")


# ── financial-analysis: dcf-model skill ──────────────────────────────────────
@app.get("/api/stock/{ticker}/dcf")
async def get_dcf(ticker: str):
    def _build():
        t_upper = ticker.upper()
        t = yf.Ticker(t_upper)
        info = t.info
        if not info or (info.get("regularMarketPrice") is None and info.get("currentPrice") is None):
            raise HTTPException(status_code=404, detail=f"Ticker '{t_upper}' not found")

        price      = round(float(float(info.get("currentPrice") or info.get("regularMarketPrice") or t.history(period="1d")["Close"].dropna().iloc[-1])), 2)
        shares_out = safe(info.get("sharesOutstanding"))

        def num(v, d=2): return f"{round(v, d)}" if v is not None else "N/A"
        def pct(v): return f"{round(v * 100, 2)}%" if v is not None else "N/A"
        def bn(v): return f"${v / 1e9:.2f}B" if v is not None else "N/A"

        return f"""You are a financial modeling expert. Build a rigorous DCF valuation analysis for {t_upper} ({info.get('longName', t_upper)}).

FINANCIAL DATA:
Current Price: ${price}
Market Cap: {bn(safe(info.get('marketCap')))}
Revenue (TTM): {bn(safe(info.get('totalRevenue')))}
Free Cash Flow (TTM): {bn(safe(info.get('freeCashflow')))}
EBITDA (TTM): {bn(safe(info.get('ebitda')))}
Net Income (TTM): {bn(safe(info.get('netIncomeToCommon')))}
Total Debt: {bn(safe(info.get('totalDebt')))} | Cash: {bn(safe(info.get('totalCash')))}
Shares Outstanding: {f"{shares_out / 1e9:.3f}B" if shares_out else "N/A"}
Beta: {num(safe(info.get('beta')))}
Revenue Growth (YoY): {pct(safe(info.get('revenueGrowth')))}
EPS Growth (YoY): {pct(safe(info.get('earningsGrowth')))}
Operating Margin: {pct(safe(info.get('operatingMargins')))} | Net Margin: {pct(safe(info.get('profitMargins')))}

Build a structured DCF analysis with these exact sections:

## Key Assumptions
(State your revenue CAGR for years 1–5, terminal growth rate g, WACC — justify each assumption with reference to the data above. Show the formula for WACC.)

## 5-Year FCF Projection
Show a markdown table:
| Year | Revenue ($B) | FCF Margin | FCF ($B) | Discount Factor | PV of FCF ($B) |

## Terminal Value & Equity Bridge
(Calculate terminal value using Gordon Growth Model, discount to PV, subtract debt, add cash → equity value, divide by shares → intrinsic value per share)

## Intrinsic Value Range
| Scenario | WACC | Terminal Growth | Fair Value | vs Current Price |
(Bear / Base / Bull cases)

## Sensitivity Table
Show a 3×3 table of fair value across WACC (rows) vs terminal growth (columns).

## Conclusion
(Is the stock cheap, fair, or expensive on a DCF basis? What is the implied margin of safety or premium?)

Show all calculations clearly. Use markdown tables. ~500 words."""

    prompt = await asyncio.to_thread(_build)
    return StreamingResponse(ollama_stream_async(prompt), media_type="text/event-stream")


# ── financial-analysis: comps-analysis skill ──────────────────────────────────
@app.get("/api/stock/{ticker}/comps")
async def get_comps(ticker: str):
    def _build():
        t_upper = ticker.upper()
        t = yf.Ticker(t_upper)
        info = t.info
        if not info or (info.get("regularMarketPrice") is None and info.get("currentPrice") is None):
            raise HTTPException(status_code=404, detail=f"Ticker '{t_upper}' not found")

        price = round(float(float(info.get("currentPrice") or info.get("regularMarketPrice") or t.history(period="1d")["Close"].dropna().iloc[-1])), 2)

        def num(v, d=2): return f"{round(v, d)}" if v is not None else "N/A"
        def pct(v): return f"{round(v * 100, 2)}%" if v is not None else "N/A"
        def bn(v): return f"${v / 1e9:.2f}B" if v is not None else "N/A"

        return f"""You are a Wall Street equity research analyst specializing in comparable companies analysis. Analyze {t_upper} ({info.get('longName', t_upper)}) against its public peers.

TARGET COMPANY — {t_upper}:
Sector: {info.get('sector', 'N/A')} | Industry: {info.get('industry', 'N/A')}
Current Price: ${price} | Market Cap: {bn(safe(info.get('marketCap')))}
Revenue (TTM): {bn(safe(info.get('totalRevenue')))}
P/E (Trailing): {num(safe(info.get('trailingPE')))} | P/E (Forward): {num(safe(info.get('forwardPE')))}
EV/EBITDA: {num(safe(info.get('enterpriseToEbitda')))} | EV/Revenue: {num(safe(info.get('enterpriseToRevenue')))}
Gross Margin: {pct(safe(info.get('grossMargins')))} | Operating Margin: {pct(safe(info.get('operatingMargins')))} | Net Margin: {pct(safe(info.get('profitMargins')))}
Revenue Growth: {pct(safe(info.get('revenueGrowth')))} | EPS Growth: {pct(safe(info.get('earningsGrowth')))}
ROE: {pct(safe(info.get('returnOnEquity')))} | Debt/Equity: {num(safe(info.get('debtToEquity')))} | FCF: {bn(safe(info.get('freeCashflow')))}

Write a professional comparable companies analysis with these exact sections:

## Peer Universe
(Name 5–6 most relevant public peers with a one-line rationale for each)

## Trading Multiples Table
Create a markdown table using your knowledge of approximate current multiples for these peers:
| Ticker | Company | P/E (Fwd) | EV/EBITDA | EV/Rev | Rev Growth | Op Margin | Grade |

Include {t_upper} as the first row, clearly labelled. Grade each A/B/C on value attractiveness.

## Premium / Discount Analysis
(Is {t_upper} trading at a premium or discount to the peer median? Quantify it. Is the premium/discount justified?)

## Fundamental Differentiators
(What makes {t_upper} stand out vs peers — better margins, faster growth, stronger balance sheet, or lagging?)

## Implied Valuation Range
(Apply peer median multiples to {t_upper}'s financials → implied price range. Show the math for P/E and EV/EBITDA.)

## Ranking Among Peers
(Rank {t_upper} in the peer group: Best in Class / Mid-Pack / Laggard — with a one-paragraph investment rationale)

Use markdown tables throughout. Be precise. ~450 words."""

    prompt = await asyncio.to_thread(_build)
    return StreamingResponse(ollama_stream_async(prompt), media_type="text/event-stream")


# ── market-researcher: sector-overview + idea-generation skills ───────────────
@app.get("/api/sector/{sector}/research")
async def get_sector_research(sector: str):
    prompt = f"""You are a senior sector analyst and portfolio strategist. Generate a comprehensive research report on the {sector} sector.

Write a structured report with these exact sections:

## Sector Snapshot
(Size, key growth drivers, current macro tailwinds — 2–3 sentences)

## Macro Tailwinds & Headwinds
**Tailwinds** (3 specific factors helping this sector right now)
**Headwinds** (3 specific risks or drags)

## Competitive Landscape
(Key players, how market share is shifting, disruptive forces, consolidation trends)

## Top Investment Themes
(3 specific investable themes within this sector generating alpha right now — be concrete)

## High Conviction Stock Ideas
List 5 stocks with a mini-thesis for each:
| Ticker | Company | Market Cap | Thesis | Key Catalyst |

## Stocks to Avoid
(2–3 names that look risky, overvalued, or structurally challenged — with reasoning)

## Valuation Assessment
(Is the sector cheap, fair, or expensive vs 5-year history? Reference key multiples: P/E, EV/EBITDA)

## 12-Month Outlook
| Scenario | Probability | Return | Key Assumptions |
Bull / Base / Bear

Be opinionated, specific, and timely. Use markdown throughout. ~600 words."""

    return StreamingResponse(ollama_stream_async(prompt), media_type="text/event-stream")


# ── Plugin-enhanced dashboard report (all 4 plugins) ─────────────────────────
@app.get("/api/stock/{ticker}/plugin-report")
async def get_plugin_report(ticker: str):
    def _build():
        t_upper = ticker.upper()
        t = yf.Ticker(t_upper)
        info = t.info
        if not info or (info.get("regularMarketPrice") is None and info.get("currentPrice") is None):
            raise HTTPException(status_code=404, detail=f"Ticker '{t_upper}' not found")

        hist      = t.history(period="1y")
        hist      = hist[hist["Close"].notna()]
        close     = hist["Close"]
        hist.ta.rsi(length=14, append=True)
        hist.ta.macd(append=True)

        price_now  = float(info.get("currentPrice") or info.get("regularMarketPrice") or close.iloc[-1])
        rsi_val    = safe(hist["RSI_14"].iloc[-1])        if "RSI_14"       in hist.columns else None
        macd_val   = safe(hist["MACD_12_26_9"].iloc[-1])  if "MACD_12_26_9"  in hist.columns else None
        signal_val = safe(hist["MACDs_12_26_9"].iloc[-1]) if "MACDs_12_26_9" in hist.columns else None
        ma50       = float(close.rolling(50).mean().iloc[-1])
        ma200      = float(close.rolling(200).mean().iloc[-1])
        vol_today  = int(hist["Volume"].iloc[-1])
        vol_avg20  = float(hist["Volume"].rolling(20).mean().iloc[-1])

        shares_out    = safe(info.get("sharesOutstanding"))
        target_mean   = safe(info.get("targetMeanPrice"))
        analyst_count = safe(info.get("numberOfAnalystOpinions"))

        analyst_recs_str = "N/A"
        try:
            recs = t.recommendations_summary
            if recs is not None and not recs.empty:
                row = recs.iloc[0]
                analyst_recs_str = (f"Strong Buy {int(row.get('strongBuy',0))}, "
                                    f"Buy {int(row.get('buy',0))}, Hold {int(row.get('hold',0))}, "
                                    f"Sell {int(row.get('sell',0))}, Strong Sell {int(row.get('strongSell',0))}")
        except Exception:
            pass

        def pct(v): return f"{round(v * 100, 2)}%" if v is not None else "N/A"
        def num(v, d=2): return f"{round(v, d)}" if v is not None else "N/A"
        def bn(v): return f"${v / 1e9:.2f}B" if v is not None else "N/A"
        upside   = f"{round((target_mean / price_now - 1) * 100, 1)}%" if target_mean else "N/A"
        macd_dir = "Bullish" if macd_val and signal_val and macd_val > signal_val else "Bearish"

        return f"""You are a senior Wall Street equity research analyst writing a full initiation-of-coverage report for {t_upper} ({info.get('longName', t_upper)}). Apply all four financial research frameworks: equity-research (initiating coverage, thesis, earnings analysis), financial-analysis (DCF valuation, comparable companies), earnings-reviewer (earnings quality and estimates), and market-researcher (sector context and competitive positioning).

═══ COMPANY DATA ═══
Company: {info.get('longName', t_upper)}
Sector: {info.get('sector', 'N/A')} | Industry: {info.get('industry', 'N/A')}
Current Price: ${round(price_now, 2)} | Market Cap: {bn(safe(info.get('marketCap')))}

═══ VALUATION (financial-analysis: dcf-model + comps-analysis) ═══
P/E Trailing: {num(safe(info.get('trailingPE')))} | P/E Forward: {num(safe(info.get('forwardPE')))}
EV/EBITDA: {num(safe(info.get('enterpriseToEbitda')))} | EV/Revenue: {num(safe(info.get('enterpriseToRevenue')))}
Revenue (TTM): {bn(safe(info.get('totalRevenue')))} | FCF (TTM): {bn(safe(info.get('freeCashflow')))} | EBITDA: {bn(safe(info.get('ebitda')))}
Debt: {bn(safe(info.get('totalDebt')))} | Cash: {bn(safe(info.get('totalCash')))} | Beta: {num(safe(info.get('beta')))}
Shares Out: {f"{shares_out/1e9:.2f}B" if shares_out else "N/A"}

═══ PROFITABILITY (financial-analysis: 3-statement-model) ═══
Gross Margin: {pct(safe(info.get('grossMargins')))} | Op Margin: {pct(safe(info.get('operatingMargins')))} | Net Margin: {pct(safe(info.get('profitMargins')))}
Revenue Growth (YoY): {pct(safe(info.get('revenueGrowth')))} | EPS Growth (YoY): {pct(safe(info.get('earningsGrowth')))}
ROE: {pct(safe(info.get('returnOnEquity')))} | Debt/Equity: {num(safe(info.get('debtToEquity')))}

═══ EARNINGS & ESTIMATES (equity-research: earnings-preview + earnings-reviewer) ═══
EPS Forward: {num(safe(info.get('epsForward')))} | Analyst Count: {analyst_count or 'N/A'}
Price Targets — Mean: ${num(target_mean)}, High: ${num(safe(info.get('targetHighPrice')))}, Low: ${num(safe(info.get('targetLowPrice')))}
Upside to Mean Target: {upside}
Analyst Recommendations: {analyst_recs_str}

═══ TECHNICALS (equity-research: catalyst-calendar + thesis-tracker) ═══
RSI (14): {num(rsi_val)} ({'Overbought' if rsi_val and rsi_val > 70 else 'Oversold' if rsi_val and rsi_val < 30 else 'Neutral'})
MACD: {num(macd_val)} | Signal: {num(signal_val)} → {macd_dir}
vs 50-Day MA: {'above' if price_now > ma50 else 'below'} (${round(ma50, 2)})
vs 200-Day MA: {'above' if price_now > ma200 else 'below'} (${round(ma200, 2)})
Volume: {vol_today/1e6:.1f}M ({round(vol_today/vol_avg20,2)}x 20-day avg)

Write a full investment research initiation report with these exact sections:

## Executive Summary
(3 sentences: overall verdict — Bullish / Neutral / Bearish — price target, and the single most important driver)

## Business Overview & Sector Context
(Company description + sector positioning using market-researcher framework: where it sits in the competitive landscape, moat, key end markets)

## DCF Valuation
(Using financial-analysis: dcf-model — state WACC assumption, 5-year revenue CAGR assumption, terminal growth rate, and derive intrinsic value per share. Compare to current price.)

## Comparable Companies Analysis
(Using financial-analysis: comps-analysis — name 4 peers, compare key multiples in a markdown table, state whether {t_upper} trades at a premium or discount and if justified)

| Peer | P/E (Fwd) | EV/EBITDA | Rev Growth | Op Margin |
(include {t_upper} as first row)

## Earnings Quality & Estimates
(Using equity-research: earnings-reviewer — assess quality of earnings, FCF conversion, estimate trajectory, analyst sentiment, and beat/miss history context)

## Profitability & Growth Assessment
(Using financial-analysis: 3-statement-model framework — revenue growth durability, margin trajectory, ROE quality, capital allocation)

## Technical Picture
(Using equity-research: catalyst-calendar + thesis-tracker — trend, momentum, key support/resistance levels, volume signal)

## Key Risks
(4 specific, numbered risks — one from each plugin's perspective: valuation risk, earnings risk, sector/competitive risk, technical risk)

## Investment Conclusion
(Clear verdict: **Bullish / Neutral / Bearish** with a 12-month price target and 2-sentence rationale)

Be direct, opinionated, and specific with numbers throughout. Use markdown formatting. ~700 words."""

    prompt = await asyncio.to_thread(_build)
    return StreamingResponse(ollama_stream_async(prompt), media_type="text/event-stream")


# ── Peer universe by yfinance industry name ────────────────────────────────────
PEER_UNIVERSE: dict[str, list[str]] = {
    "Semiconductors":                         ["NVDA","AMD","INTC","QCOM","AVGO","MRVL","MU","TXN","LRCX","AMAT"],
    "Software—Application":                   ["MSFT","ORCL","ADBE","CRM","INTU","WDAY","NOW","HUBS"],
    "Software—Infrastructure":                ["MSFT","ORCL","IBM","PANW","CRWD","ZS","FTNT","NET"],
    "Internet Content & Information":         ["GOOGL","META","SNAP","PINS","IAC","RDDT"],
    "Consumer Electronics":                   ["AAPL","MSFT","DELL","HPQ","SONY"],
    "Electronic Gaming & Multimedia":         ["EA","TTWO","RBLX","NTDOY","SONY"],
    "Banks—Diversified":                      ["JPM","BAC","WFC","C","USB","PNC","TFC"],
    "Banks—Regional":                         ["USB","PNC","RF","CFG","KEY","FITB","HBAN"],
    "Insurance—Diversified":                  ["BRK-B","MET","PRU","AIG","ALL","TRV"],
    "Insurance—Life":                         ["MET","PRU","LNC","SFG","GL"],
    "Drug Manufacturers—General":             ["JNJ","PFE","MRK","ABBV","LLY","BMY","AZN"],
    "Drug Manufacturers—Specialty & Generic": ["AMGN","GILD","REGN","BIIB","VRTX","MRNA"],
    "Biotechnology":                          ["AMGN","GILD","REGN","BIIB","VRTX","MRNA","SGEN"],
    "Medical Devices":                        ["MDT","ABT","SYK","BSX","EW","ZBH","ISRG"],
    "Oil & Gas Integrated":                   ["XOM","CVX","BP","SHEL","TTE","ENB"],
    "Oil & Gas E&P":                          ["PXD","COP","DVN","EOG","OXY","FANG"],
    "Specialty Retail":                       ["AMZN","WMT","TGT","COST","HD","LOW","BBY"],
    "Discount Stores":                        ["WMT","COST","TGT","DG","DLTR"],
    "Auto Manufacturers":                     ["TSLA","GM","F","STLA","TM","HMC"],
    "Airlines":                               ["DAL","UAL","AAL","LUV","ALK"],
    "Telecom Services":                       ["T","VZ","TMUS","CMCSA","CHTR"],
    "Aerospace & Defense":                    ["LMT","RTX","NOC","GD","BA","LHX"],
    "Healthcare Plans":                       ["UNH","CVS","HUM","CNC","MOH","ELV"],
    "REIT—Diversified":                       ["AMT","PLD","CCI","EQIX","SPG","PSA","O"],
    "Entertainment":                          ["DIS","NFLX","PARA","WBD","CMCSA"],
    "Restaurants":                            ["MCD","SBUX","YUM","CMG","DPZ","QSR"],
    "Capital Markets":                        ["GS","MS","JPM","BAC","C","SCHW"],
    "Asset Management":                       ["BLK","BX","KKR","APO","ARES"],
    "Utilities—Regulated Electric":           ["NEE","DUK","SO","AEP","EXC","D"],
    "Integrated Freight & Logistics":         ["UPS","FDX","XPO","GXO","CHRW"],
    "Travel Services":                        ["BKNG","EXPE","ABNB","TRIP","MMYT"],
}


def _dcf_iv(fcf_ttm: float, growth: float, wacc: float, term_g: float,
            net_debt: float, shares: float) -> float | None:
    if wacc <= term_g:
        return None
    fcf = fcf_ttm
    pv_sum = 0.0
    for yr in range(1, 6):
        fcf *= (1 + growth)
        pv_sum += fcf / (1 + wacc) ** yr
    tv    = fcf * (1 + term_g) / (wacc - term_g)
    pv_tv = tv / (1 + wacc) ** 5
    return (pv_sum + pv_tv - net_debt) / shares


@app.get("/api/stock/{ticker}/dcf-data")
def get_dcf_data(ticker: str):
    ticker = ticker.upper()
    t = yf.Ticker(ticker)
    info = t.info

    if not info or (info.get("regularMarketPrice") is None and info.get("currentPrice") is None):
        raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' not found")

    price      = float(info.get("currentPrice") or info.get("regularMarketPrice"))
    beta       = float(safe(info.get("beta")) or 1.0)
    shares_out = safe(info.get("sharesOutstanding"))
    market_cap = safe(info.get("marketCap"))
    total_debt = float(safe(info.get("totalDebt")) or 0)
    total_cash = float(safe(info.get("totalCash")) or 0)
    tax_rate   = float(safe(info.get("effectiveTaxRate")) or 0.21)
    tax_rate   = max(0.05, min(tax_rate, 0.40))

    # TTM FCF: sum last 4 quarters
    fcf_ttm = None
    try:
        cf_q = t.quarterly_cashflow
        if "Free Cash Flow" in cf_q.index:
            last4 = cf_q.loc["Free Cash Flow"].iloc[:4].dropna()
            if len(last4) >= 3:
                fcf_ttm = float(last4.sum())
    except Exception:
        pass
    if fcf_ttm is None:
        fcf_ttm = safe(info.get("freeCashflow"))
    if fcf_ttm is None or fcf_ttm <= 0:
        raise HTTPException(status_code=422, detail="DCF requires positive trailing FCF — this company does not qualify")

    # Annual FCF history (oldest → newest)
    fcf_history: list[dict] = []
    try:
        cf_a = t.cashflow
        if "Free Cash Flow" in cf_a.index:
            rows = [(col, float(cf_a.loc["Free Cash Flow", col])) for col in cf_a.columns[:4]
                    if not pd.isna(cf_a.loc["Free Cash Flow", col])]
            rows.reverse()
            fcf_history = [{"year": col.year, "fcf": round(v / 1e9, 2)} for col, v in rows]
    except Exception:
        pass

    # Historical FCF CAGR
    hist_cagr = None
    valid = [x for x in fcf_history if x["fcf"] > 0]
    if len(valid) >= 2:
        span = valid[-1]["year"] - valid[0]["year"]
        if span > 0:
            hist_cagr = (valid[-1]["fcf"] / valid[0]["fcf"]) ** (1 / span) - 1

    # WACC via CAPM
    rf, erp = 0.043, 0.055
    ke = rf + beta * erp
    kd = 0.045
    try:
        inc = t.income_stmt
        for key in ["Interest Expense", "Interest Expense Non Operating"]:
            if key in inc.index and total_debt > 0:
                ie = abs(float(inc.loc[key].iloc[0]))
                if not pd.isna(ie) and ie > 0:
                    kd = min(ie / total_debt, 0.15)
                    break
    except Exception:
        pass

    equity_val = float(market_cap) if market_cap else (shares_out * price if shares_out else None)
    if equity_val and total_debt > 0:
        total_cap = equity_val + total_debt
        we, wd    = equity_val / total_cap, total_debt / total_cap
        wacc      = we * ke + wd * kd * (1 - tax_rate)
    else:
        wacc, we, wd = ke, 1.0, 0.0
    wacc = max(0.06, min(wacc, 0.22))

    # Growth scenarios — capped at realistic ceilings
    if hist_cagr and hist_cagr > 0:
        bear_g = min(hist_cagr * 0.25, 0.15)
        base_g = min(hist_cagr * 0.50, 0.30)
        bull_g = min(hist_cagr * 0.80, 0.50)
    else:
        rev_g  = float(safe(info.get("revenueGrowth")) or 0.05)
        bear_g = max(0.0,  min(rev_g * 0.3, 0.10))
        base_g = max(0.03, min(rev_g * 0.6, 0.20))
        bull_g = max(0.07, min(rev_g * 0.9, 0.35))

    net_debt = total_debt - total_cash
    shares   = float(shares_out) if shares_out else (equity_val / price if equity_val and price else None)
    if not shares:
        raise HTTPException(status_code=422, detail="Could not determine shares outstanding")

    scenarios: dict = {}
    for name, growth, term_g in [("bear", bear_g, 0.020), ("base", base_g, 0.025), ("bull", bull_g, 0.030)]:
        fcf_proj = fcf_ttm
        pv_sum, projections = 0.0, []
        for yr in range(1, 6):
            fcf_proj *= (1 + growth)
            pv = fcf_proj / (1 + wacc) ** yr
            pv_sum += pv
            projections.append({"year": f"Y{yr}", "fcf": round(fcf_proj / 1e9, 2), "pv": round(pv / 1e9, 2)})
        pv_tv = (fcf_proj * (1 + term_g) / (wacc - term_g)) / (1 + wacc) ** 5 if wacc > term_g else 0.0
        iv    = (pv_sum + pv_tv - net_debt) / shares
        scenarios[name] = {
            "growthRate":     round(growth * 100, 1),
            "terminalGrowth": round(term_g * 100, 1),
            "pvFcfs":         round(pv_sum / 1e9, 2),
            "pvTerminal":     round(pv_tv / 1e9, 2),
            "totalPv":        round((pv_sum + pv_tv) / 1e9, 2),
            "intrinsicValue": round(iv, 2),
            "upside":         round((iv / price - 1) * 100, 1),
            "projections":    projections,
        }

    # Sensitivity: WACC ± 2% vs terminal growth 1.5–3.5%
    wacc_vals = [round(wacc + d, 4) for d in (-0.02, -0.01, 0.0, 0.01, 0.02)]
    term_vals = [0.015, 0.020, 0.025, 0.030, 0.035]
    grid = [
        [round(_dcf_iv(fcf_ttm, base_g, w, tg, net_debt, shares), 2)
         if _dcf_iv(fcf_ttm, base_g, w, tg, net_debt, shares) else None
         for tg in term_vals]
        for w in wacc_vals
    ]

    return {
        "ticker":        ticker,
        "price":         round(price, 2),
        "fcfTtm":        round(fcf_ttm / 1e9, 2),
        "netDebtB":      round(net_debt / 1e9, 2),
        "sharesB":       round(shares / 1e9, 3),
        "assumptions": {
            "wacc":         round(wacc * 100, 2),
            "costOfEquity": round(ke * 100, 2),
            "costOfDebt":   round(kd * 100, 2),
            "beta":         round(beta, 2),
            "riskFreeRate": round(rf * 100, 2),
            "taxRate":      round(tax_rate * 100, 1),
            "weightEquity": round(we * 100, 1),
            "weightDebt":   round(wd * 100, 1),
        },
        "historicalCagr": round(hist_cagr * 100, 1) if hist_cagr else None,
        "fcfHistory":     fcf_history,
        "scenarios":      scenarios,
        "sensitivity": {
            "waccRates": [round(w * 100, 2) for w in wacc_vals],
            "termRates":  [round(tg * 100, 1) for tg in term_vals],
            "grid":       grid,
        },
    }


@app.get("/api/stock/{ticker}/comps-data")
def get_comps_data(ticker: str):
    ticker = ticker.upper()
    t = yf.Ticker(ticker)
    info = t.info

    if not info or (info.get("regularMarketPrice") is None and info.get("currentPrice") is None):
        raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' not found")

    industry = info.get("industry", "")
    peers_raw = [p for p in PEER_UNIVERSE.get(industry, []) if p != ticker][:6]

    def _row(sym: str, pi: dict) -> dict:
        px  = float(pi.get("currentPrice") or pi.get("regularMarketPrice") or 0)
        mc  = safe(pi.get("marketCap"))
        return {
            "ticker":    sym,
            "name":      pi.get("longName", sym),
            "marketCapB": round(mc / 1e9, 1) if mc else None,
            "price":     round(px, 2),
            "fwdPE":     round(safe(pi.get("forwardPE")), 1)              if safe(pi.get("forwardPE"))     else None,
            "evEbitda":  round(safe(pi.get("enterpriseToEbitda")), 1)     if safe(pi.get("enterpriseToEbitda")) else None,
            "evRevenue": round(safe(pi.get("enterpriseToRevenue")), 2)    if safe(pi.get("enterpriseToRevenue")) else None,
            "revGrowth": round(safe(pi.get("revenueGrowth")) * 100, 1)    if safe(pi.get("revenueGrowth"))  else None,
            "opMargin":  round(safe(pi.get("operatingMargins")) * 100, 1) if safe(pi.get("operatingMargins")) else None,
            "netMargin": round(safe(pi.get("profitMargins")) * 100, 1)    if safe(pi.get("profitMargins"))  else None,
        }

    target = _row(ticker, info)

    peer_rows = []
    for sym in peers_raw:
        try:
            pi = yf.Ticker(sym).info
            if pi and (pi.get("regularMarketPrice") or pi.get("currentPrice")):
                peer_rows.append(_row(sym, pi))
        except Exception:
            pass

    def _median(key: str) -> float | None:
        vals = sorted(r[key] for r in peer_rows if r.get(key) is not None)
        if not vals:
            return None
        mid = len(vals) // 2
        return vals[mid] if len(vals) % 2 else round((vals[mid - 1] + vals[mid]) / 2, 2)

    peer_median = {k: _median(k) for k in ("fwdPE", "evEbitda", "evRevenue", "revGrowth", "opMargin", "netMargin")}

    # Implied prices from peer-median multiples
    price_t    = target["price"]
    eps_fwd    = safe(info.get("epsForward"))
    ebitda     = safe(info.get("ebitda"))
    revenue    = safe(info.get("totalRevenue"))
    net_debt_t = float(safe(info.get("totalDebt")) or 0) - float(safe(info.get("totalCash")) or 0)
    shares_t   = safe(info.get("sharesOutstanding"))
    implied: dict = {}

    if peer_median["fwdPE"] and eps_fwd and eps_fwd > 0:
        iv = round(peer_median["fwdPE"] * eps_fwd, 2)
        implied["byFwdPE"] = {"impliedPrice": iv, "upside": round((iv / price_t - 1) * 100, 1)}

    if peer_median["evEbitda"] and ebitda and shares_t:
        iv = round((peer_median["evEbitda"] * ebitda - net_debt_t) / shares_t, 2)
        implied["byEVEBITDA"] = {"impliedPrice": iv, "upside": round((iv / price_t - 1) * 100, 1)}

    if peer_median["evRevenue"] and revenue and shares_t:
        iv = round((peer_median["evRevenue"] * revenue - net_debt_t) / shares_t, 2)
        implied["byEVRevenue"] = {"impliedPrice": iv, "upside": round((iv / price_t - 1) * 100, 1)}

    return {
        "ticker":     ticker,
        "industry":   industry,
        "target":     target,
        "peers":      peer_rows,
        "peerMedian": peer_median,
        "implied":    implied,
    }


# ── Portfolio endpoints ───────────────────────────────────────────────────────

class PositionInput(BaseModel):
    ticker:       str
    shares:       float
    purchaseDate: str   # "YYYY-MM-DD"

class PortfolioRequest(BaseModel):
    positions: List[PositionInput]


@app.post("/api/portfolio/performance")
def get_portfolio_performance(body: PortfolioRequest):
    if not body.positions:
        raise HTTPException(status_code=422, detail="No positions provided")

    today        = pd.Timestamp.now().normalize()
    one_year_ago = today - pd.Timedelta(days=365)

    parsed = []
    for p in body.positions:
        try:
            dt = pd.Timestamp(p.purchaseDate).normalize()
        except Exception:
            dt = one_year_ago
        parsed.append({"ticker": p.ticker.upper(), "shares": p.shares, "date": dt})

    earliest  = min(p["date"] for p in parsed)
    start_str = earliest.strftime("%Y-%m-%d")
    end_str   = (today + pd.Timedelta(days=1)).strftime("%Y-%m-%d")

    # Fetch per-ticker using Ticker.history() — consistent across yfinance versions
    fetch_syms = list(set(p["ticker"] for p in parsed) | {"SPY"})
    price_cols: dict[str, pd.Series] = {}
    for sym in fetch_syms:
        try:
            hist = yf.Ticker(sym).history(start=start_str, end=end_str)
            if hist.empty:
                continue
            idx = hist.index.tz_localize(None) if hist.index.tz is not None else hist.index
            hist.index = idx
            price_cols[sym] = hist["Close"].rename(sym)
        except Exception:
            pass

    if not price_cols or not any(p["ticker"] in price_cols for p in parsed):
        raise HTTPException(status_code=422, detail="Could not fetch price history for any position")

    # Align all series onto a common date index, forward-fill gaps
    prices = pd.DataFrame(price_cols).sort_index().ffill().bfill()

    # Build daily portfolio NAV
    nav_rows = []
    for date, row in prices.iterrows():
        value = 0.0
        for p in parsed:
            if date < p["date"]:
                continue
            px = row.get(p["ticker"])
            if px is None or pd.isna(px):
                continue
            value += p["shares"] * float(px)
        if value > 0:
            nav_rows.append({"date": date, "value": value})

    if not nav_rows:
        raise HTTPException(status_code=422, detail="Could not compute portfolio history")

    # Normalise SPY benchmark to portfolio's starting value
    start_value = nav_rows[0]["value"]
    start_date  = nav_rows[0]["date"]

    spy_series  = prices["SPY"] if "SPY" in prices.columns else None
    spy_start: float | None = None
    if spy_series is not None:
        candidates = spy_series.loc[spy_series.index >= start_date].dropna()
        if not candidates.empty:
            spy_start = float(candidates.iloc[0])

    chart = []
    for n in nav_rows:
        point: dict = {"date": n["date"].strftime("%Y-%m-%d"), "value": round(n["value"], 2)}
        if spy_start and spy_series is not None:
            sp = spy_series.get(n["date"])
            if sp is not None and not pd.isna(sp):
                point["benchmark"] = round(start_value * float(sp) / spy_start, 2)
        chart.append(point)

    end_value = chart[-1]["value"]
    total_ret = (end_value / start_value - 1) * 100

    bench_ret: float | None = None
    if len(chart) > 1 and "benchmark" in chart[-1] and "benchmark" in chart[0]:
        bench_ret = (chart[-1]["benchmark"] / chart[0]["benchmark"] - 1) * 100

    return {
        "chart": chart,
        "stats": {
            "startDate":       start_date.strftime("%Y-%m-%d"),
            "startValue":      round(start_value, 2),
            "currentValue":    round(end_value, 2),
            "totalReturn":     round(total_ret, 2),
            "benchmarkReturn": round(bench_ret, 2) if bench_ret is not None else None,
            "alpha":           round(total_ret - bench_ret, 2) if bench_ret is not None else None,
        },
    }


# ── Portfolio batch-price endpoint ────────────────────────────────────────────
@app.get("/api/portfolio/prices")
def get_portfolio_prices(tickers: str):
    """Return price, daily change, and name for a comma-separated list of tickers."""
    result: dict = {}
    for sym in tickers.upper().split(","):
        sym = sym.strip()
        if not sym:
            continue
        try:
            info = yf.Ticker(sym).info
            if not info:
                continue
            price = float(info.get("currentPrice") or info.get("regularMarketPrice") or 0)
            prev  = float(info.get("previousClose") or info.get("regularMarketPreviousClose") or price)
            result[sym] = {
                "price":     round(price, 2),
                "prevClose": round(prev, 2),
                "changePct": round((price / prev - 1) * 100, 2) if prev else 0.0,
                "name":      info.get("longName", sym),
            }
        except Exception:
            pass
    return {"prices": result}


# ══════════════════════════════════════════════════════════════════════════════
#  ARM — Adaptive Regime Momentum  (Phase 2 optimized parameters)
#  ADX trend=22, ADX range=15, RSI<30, Mom>=10%, 8 momentum slots + 4 MR slots
#  Rebalance: bi-weekly  |  Backtest: 25.4% CAGR, Sharpe 1.14, p<0.05
# ══════════════════════════════════════════════════════════════════════════════

ARM_UNIVERSE = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA",
    "AVGO", "AMD",  "QCOM", "TXN",  "INTC",  "MU",   "AMAT", "LRCX", "KLAC", "MRVL",
    "CRM",  "ADBE", "INTU", "NOW",  "ORCL",  "PLTR", "CRWD", "NET",  "DDOG", "ZS",  "SNOW",
    "CSCO", "IBM",  "ACN",
    "JPM",  "BAC",  "GS",   "MS",   "WFC",   "C",
    "V",    "MA",   "AXP",  "BLK",  "BX",    "CME",  "USB",  "COF",
    "UNH",  "CI",   "HUM",  "CVS",
    "JNJ",  "LLY",  "ABBV", "MRK",  "AMGN",  "BMY",  "GILD", "PFE",  "REGN", "VRTX",
    "TMO",  "ISRG", "SYK",  "ZTS",  "ABT",   "DHR",  "MDT",
    "HD",   "MCD",  "SBUX", "NKE",  "BKNG",  "TGT",  "LOW",  "ABNB", "CMG",
    "WMT",  "COST", "PG",   "KO",   "PEP",   "PM",   "MO",   "MDLZ", "CL",
    "CVX",  "XOM",  "OXY",  "COP",  "SLB",
    "CAT",  "DE",   "HON",  "UNP",  "LMT",   "RTX",  "NOC",  "BA",   "EMR",  "GE",
    "VZ",   "T",    "DIS",  "NFLX", "CMCSA",
    "NEE",  "DUK",  "SO",
    "AMT",  "PLD",  "EQIX",
    "F",    "GM",   "PYPL",
]

_ARM_P = {
    "adx_trend": 22, "adx_range": 15, "rsi_os": 30,
    "bb_pct": 0.25,  "vol_spike": 1.3, "mom_min": 0.10,
    "mom_slots": 8,  "mr_slots": 4,
}

_arm_cache: dict = {"data": None, "ts": None}
ARM_CACHE_TTL = 3600  # seconds


def _score_ticker(ticker: str, close, high, low, volume) -> dict | None:
    """Compute ARM signals for a single ticker. Returns None if insufficient data."""
    c = close.dropna()
    h = high.reindex(c.index)
    l = low.reindex(c.index)
    v = volume.reindex(c.index)
    if len(c) < 300:
        return None
    try:
        adx_s, plus_di, minus_di = compute_adx(h, l, c)
        rsi_s                    = compute_rsi(c)
        _, _, _, bb_s            = compute_bollinger_bands(c)
        mom_s                    = compute_momentum_12_1(c)
        vol_s                    = compute_volume_ratio(v)

        adx  = float(adx_s.iloc[-1]);   pdi = float(plus_di.iloc[-1])
        mdi  = float(minus_di.iloc[-1]); rsi = float(rsi_s.iloc[-1])
        bb   = float(bb_s.iloc[-1]);     mom = float(mom_s.iloc[-1])
        vol  = float(vol_s.iloc[-1])

        if any(np.isnan(x) for x in [adx, pdi, mdi, rsi, bb, mom, vol]):
            return None

        p = _ARM_P
        regime = "TRENDING" if adx >= p["adx_trend"] else ("RANGING" if adx < p["adx_range"] else "NEUTRAL")

        signal = "-"
        if regime == "TRENDING" and pdi > mdi and mom >= p["mom_min"]:
            signal = "MOM_BUY"
        elif regime == "NEUTRAL" and pdi > mdi and mom >= p["mom_min"]:
            signal = "MOM_BUY"
        elif pdi > mdi and mom > 0:
            signal = "WATCH"
        if regime == "RANGING" and rsi < p["rsi_os"] and bb < p["bb_pct"] and vol > p["vol_spike"]:
            signal = "MR_BUY"

        return {
            "ticker":   ticker,
            "regime":   regime,
            "signal":   signal,
            "momentum": round(mom * 100, 1),
            "adx":      round(adx, 1),
            "rsi":      round(rsi, 1),
            "vol_ratio": round(vol, 2),
            "plus_di":  round(pdi, 1),
            "minus_di": round(mdi, 1),
            "price":    round(float(c.iloc[-1]), 2),
        }
    except Exception:
        return None


def _compute_arm_signals() -> dict:
    """Download data and score all 113 universe stocks. Takes ~30-60 seconds."""
    tickers = list(set(ARM_UNIVERSE))
    raw = yf.download(tickers, period="18mo", auto_adjust=True, progress=False)

    if isinstance(raw.columns, pd.MultiIndex):
        close  = raw["Close"].ffill()
        high   = raw["High"].ffill()
        low    = raw["Low"].ffill()
        volume = raw["Volume"].ffill()
    else:
        raise RuntimeError("Unexpected yfinance response format")

    rows = []
    for ticker in close.columns:
        result = _score_ticker(ticker, close[ticker], high[ticker], low[ticker], volume[ticker])
        if result:
            rows.append(result)

    rows.sort(key=lambda x: x["momentum"], reverse=True)
    for i, r in enumerate(rows):
        r["rank"] = i + 1

    p = _ARM_P
    mom_buys  = [r for r in rows if r["signal"] == "MOM_BUY"][:p["mom_slots"]]
    mom_set   = {r["ticker"] for r in mom_buys}
    mr_cands  = [r for r in rows if r["signal"] == "MR_BUY" and r["ticker"] not in mom_set]
    mr_buys   = sorted(mr_cands, key=lambda x: x["rsi"])[:p["mr_slots"]]
    pick_set  = mom_set | {r["ticker"] for r in mr_buys}

    for r in rows:
        r["in_portfolio"] = r["ticker"] in pick_set

    return {
        "momentum_picks": mom_buys,
        "mr_picks":       mr_buys,
        "all_stocks":     rows,
    }


@app.get("/api/arm/signals")
def get_arm_signals(refresh: bool = False):
    """Return ARM signal scan for the full universe. Cached for 1 hour."""
    global _arm_cache
    now = datetime.now()

    if (
        not refresh
        and _arm_cache["data"]
        and _arm_cache["ts"]
        and (now - _arm_cache["ts"]).seconds < ARM_CACHE_TTL
    ):
        data = dict(_arm_cache["data"])
        data["generated_at"]      = _arm_cache["ts"].isoformat()
        data["cache_age_minutes"] = round((now - _arm_cache["ts"]).seconds / 60, 1)
        data["cached"]            = True
        return data

    try:
        result = _compute_arm_signals()
        _arm_cache["data"] = result
        _arm_cache["ts"]   = now
        out = dict(result)
        out["generated_at"]      = now.isoformat()
        out["cache_age_minutes"] = 0
        out["cached"]            = False
        return out
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ARM compute error: {e}")


@app.get("/api/arm/stock/{ticker}")
def get_arm_stock(ticker: str):
    """Return ARM signal for a single ticker. Uses cache if available, else computes."""
    ticker = ticker.upper()

    if _arm_cache["data"]:
        match = next((r for r in _arm_cache["data"]["all_stocks"] if r["ticker"] == ticker), None)
        if match:
            return match

    try:
        raw = yf.download(ticker, period="18mo", auto_adjust=True, progress=False)
        if raw.empty:
            raise HTTPException(status_code=404, detail=f"No data for {ticker}")

        if isinstance(raw.columns, pd.MultiIndex):
            c = raw["Close"].ffill().squeeze()
            h = raw["High"].ffill().squeeze()
            l = raw["Low"].ffill().squeeze()
            v = raw["Volume"].ffill().squeeze()
        else:
            c = raw["Close"].ffill()
            h = raw["High"].ffill()
            l = raw["Low"].ffill()
            v = raw["Volume"].ffill()

        result = _score_ticker(ticker, c, h, l, v)
        if not result:
            raise HTTPException(status_code=400, detail="Not enough price history")

        result["in_portfolio"] = ticker in ARM_UNIVERSE
        result["rank"]         = None
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
