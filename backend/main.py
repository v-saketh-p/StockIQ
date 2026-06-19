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
from typing import List

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
    op_margin     = safe(info.get("operatingMargins"))
    net_margin    = safe(info.get("profitMargins"))
    rev_growth    = safe(info.get("revenueGrowth"))
    eps_growth    = safe(info.get("earningsGrowth"))
    # info.freeCashflow is stale for many tickers; pull directly from the cash flow statement
    free_cf = None
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
