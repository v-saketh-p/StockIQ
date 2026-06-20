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
import os
from typing import List
from dotenv import load_dotenv

load_dotenv()
GROQ_API_KEY   = os.getenv("GROQ_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

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


REPORT_CSS = """
/* ── Themeable custom properties (light defaults) ── */
:root {
  --r-bg:          #ffffff;
  --r-surface:     #f9fafb;
  --r-raised:      #ffffff;
  --r-border:      #e5e7eb;
  --r-border-sub:  #f3f4f6;
  --r-text:        #1a1a1a;
  --r-muted:       #6b7280;
  --r-sub:         #9ca3af;
  /* Badges */
  --r-green-bg:    #f0fdf4; --r-green-fg:    #15803d; --r-green-br:    #86efac;
  --r-amber-bg:    #fff8e6; --r-amber-fg:    #b45309; --r-amber-br:    #fcd34d;
  --r-red-bg:      #fef2f2; --r-red-fg:      #b91c1c; --r-red-br:      #fca5a5;
  --r-blue-bg:     #eff6ff; --r-blue-fg:     #1d4ed8; --r-blue-br:     #93c5fd;
  /* Verdict / flag / final */
  --r-vg-bg:       #f0fdf4; --r-va-bg:       #fffbeb; --r-vr-bg:       #fef2f2;
  --r-flag-bg:     #fffbeb;
  --r-final-bg:    #fffbeb; --r-final-br:    #d97706;
  --r-opt-bg:      #f0fdf4; --r-opt-br:      #86efac;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; font-size: 14px; color: var(--r-text); background: var(--r-bg); padding: 24px; max-width: 900px; margin: 0 auto; }
h1 { font-size: 22px; font-weight: 600; margin-bottom: 4px; color: var(--r-text); }
.meta { color: var(--r-muted); font-size: 13px; margin-bottom: 20px; }
.badges { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 20px; }
.badge { font-size: 11px; font-weight: 600; padding: 3px 10px; border-radius: 20px; display: inline-block; }
.badge-green { background: var(--r-green-bg); color: var(--r-green-fg); border: 1px solid var(--r-green-br); }
.badge-amber { background: var(--r-amber-bg); color: var(--r-amber-fg); border: 1px solid var(--r-amber-br); }
.badge-red   { background: var(--r-red-bg);   color: var(--r-red-fg);   border: 1px solid var(--r-red-br);   }
.badge-blue  { background: var(--r-blue-bg);  color: var(--r-blue-fg);  border: 1px solid var(--r-blue-br);  }
.card-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 10px; margin: 14px 0; }
.card { background: var(--r-surface); border: 1px solid var(--r-border); border-radius: 8px; padding: 12px; }
.card-label { font-size: 11px; color: var(--r-muted); margin-bottom: 4px; }
.card-value { font-size: 18px; font-weight: 600; color: var(--r-text); }
.card-sub { font-size: 11px; color: var(--r-sub); margin-top: 2px; }
.section { margin: 28px 0 0; }
.section-title { font-size: 17px; font-weight: 600; border-bottom: 1px solid var(--r-border); padding-bottom: 7px; margin-bottom: 14px; color: var(--r-text); }
.sub-title { font-size: 12px; font-weight: 600; color: var(--r-muted); text-transform: uppercase; letter-spacing: 0.05em; margin: 16px 0 6px; }
.raised { background: var(--r-raised); border: 1px solid var(--r-border); border-radius: 10px; padding: 14px 16px; margin: 10px 0; }
.row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
table { width: 100%; border-collapse: collapse; font-size: 13px; margin: 10px 0; }
th { text-align: left; color: var(--r-muted); font-weight: 600; padding: 7px 8px; border-bottom: 1px solid var(--r-border); background: var(--r-surface); }
td { padding: 7px 8px; border-bottom: 1px solid var(--r-border-sub); vertical-align: top; color: var(--r-text); }
.verdict { border-left: 3px solid; padding: 12px 14px; margin: 12px 0; border-radius: 0 6px 6px 0; }
.v-green { border-color: #16a34a; background: var(--r-vg-bg); }
.v-amber { border-color: #d97706; background: var(--r-va-bg); }
.v-red   { border-color: #dc2626; background: var(--r-vr-bg); }
.flag { background: var(--r-flag-bg); border-left: 3px solid #d97706; border-radius: 0 6px 6px 0; padding: 12px 14px; margin: 12px 0; }
.final { text-align: center; padding: 28px; border: 2px solid var(--r-final-br); border-radius: 10px; margin: 20px 0; background: var(--r-final-bg); }
.final h2 { font-size: 20px; font-weight: 700; color: var(--r-text); }
p { margin: 6px 0; line-height: 1.6; color: var(--r-text); }
strong { font-weight: 600; color: var(--r-text); }
.risk-item { border-left: 3px solid; padding: 10px 14px; margin: 8px 0; border-radius: 0 4px 4px 0; }
.risk-high { border-color: #dc2626; background: var(--r-vr-bg); }
.risk-med  { border-color: #d97706; background: var(--r-va-bg); }
.risk-low  { border-color: #16a34a; background: var(--r-vg-bg); }
ul.check { padding: 0; list-style: none; }
ul.check li { padding: 3px 0; color: var(--r-text); }
ul.check li::before { content: "☐ "; }
.opt { background: var(--r-opt-bg); border: 1px solid var(--r-opt-br); border-radius: 8px; padding: 12px 14px; margin: 10px 0; }
ul { padding-left: 18px; margin: 8px 0; }
li { margin: 4px 0; line-height: 1.5; color: var(--r-text); }
@media (max-width: 600px) { .row { grid-template-columns: 1fr; } }
"""

@app.get("/api/stock/{ticker}/report")
def get_stock_report(ticker: str):
    ticker = ticker.upper()
    t      = yf.Ticker(ticker)
    info   = t.info

    if not info or (info.get("regularMarketPrice") is None and info.get("currentPrice") is None):
        raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' not found")

    hist = t.history(period="1y")
    hist = hist[hist["Close"].notna()]
    if hist.empty:
        raise HTTPException(status_code=404, detail="No price history available")

    close = hist["Close"]
    hist.ta.rsi(length=14, append=True)
    hist.ta.macd(append=True)

    rsi_val    = safe(hist["RSI_14"].iloc[-1])        if "RSI_14"       in hist.columns else None
    macd_val   = safe(hist["MACD_12_26_9"].iloc[-1])  if "MACD_12_26_9"  in hist.columns else None
    signal_val = safe(hist["MACDs_12_26_9"].iloc[-1]) if "MACDs_12_26_9" in hist.columns else None
    macd_hist  = safe(hist["MACDh_12_26_9"].iloc[-1]) if "MACDh_12_26_9" in hist.columns else None

    price_now   = float(info.get("currentPrice") or info.get("regularMarketPrice") or close.iloc[-1])
    ma50        = float(close.rolling(50).mean().iloc[-1])
    ma100       = float(close.rolling(100).mean().iloc[-1])
    ma200       = float(close.rolling(200).mean().iloc[-1])
    week52_high = float(close.max())
    week52_low  = float(close.min())
    pct_52w     = round(price_now / week52_high * 100, 1) if week52_high else None
    yr_return   = round((price_now / float(close.iloc[0]) - 1) * 100, 1) if len(close) > 1 else None

    vol_today = int(hist["Volume"].iloc[-1])
    vol_avg20 = float(hist["Volume"].rolling(20).mean().iloc[-1])
    vol_ratio = round(vol_today / vol_avg20, 2) if vol_avg20 else None

    # Relative strength vs SPY — use actual dates, not iloc offsets
    rs_3m = rs_6m = None
    try:
        spy_hist = yf.Ticker("SPY").history(period="1y")["Close"].dropna()

        # Strip timezones for simple comparison
        def strip_tz(s):
            return s.copy().set_axis(s.index.tz_localize(None) if s.index.tz is None else s.index.tz_convert(None))

        c   = strip_tz(close)
        spy = strip_tz(spy_hist)
        now_ts   = pd.Timestamp.now()
        ago_3m   = now_ts - pd.DateOffset(months=3)
        ago_6m   = now_ts - pd.DateOffset(months=6)

        def price_at(series, target):
            sub = series[series.index >= target]
            return float(sub.iloc[0]) if not sub.empty else None

        c_3m   = price_at(c,   ago_3m);  c_6m   = price_at(c,   ago_6m)
        spy_3m = price_at(spy, ago_3m);  spy_6m = price_at(spy, ago_6m)
        spy_now = float(spy.iloc[-1])

        if c_3m and spy_3m:
            rs_3m = round((price_now / c_3m - 1) * 100 - (spy_now / spy_3m - 1) * 100, 1)
        if c_6m and spy_6m:
            rs_6m = round((price_now / c_6m - 1) * 100 - (spy_now / spy_6m - 1) * 100, 1)
    except Exception:
        pass

    # Fundamentals
    roe           = safe(info.get("returnOnEquity"))
    roa           = safe(info.get("returnOnAssets"))
    gross_margin  = safe(info.get("grossMargins"))
    gross_margin  = gross_margin if (gross_margin and gross_margin > 0.001) else None
    op_margin     = safe(info.get("operatingMargins"))
    net_margin    = safe(info.get("profitMargins"))
    rev_growth    = safe(info.get("revenueGrowth"))
    eps_growth    = safe(info.get("earningsGrowth"))
    free_cf       = safe(info.get("freeCashflow"))
    op_cashflow   = safe(info.get("operatingCashflow"))
    debt_eq       = safe(info.get("debtToEquity"))
    current_ratio = safe(info.get("currentRatio"))
    pe_trailing   = safe(info.get("trailingPE"))
    pe_forward    = safe(info.get("forwardPE"))
    peg_ratio     = safe(info.get("pegRatio"))
    ev_ebitda     = safe(info.get("enterpriseToEbitda"))
    ev_revenue    = safe(info.get("enterpriseToRevenue"))
    market_cap    = safe(info.get("marketCap"))
    beta          = safe(info.get("beta"))
    total_rev     = safe(info.get("totalRevenue"))
    ebitda        = safe(info.get("ebitda"))
    net_income    = safe(info.get("netIncomeToCommon"))
    total_debt    = safe(info.get("totalDebt"))
    total_cash    = safe(info.get("totalCash"))
    total_assets  = safe(info.get("totalAssets"))
    shares_out    = safe(info.get("sharesOutstanding"))
    shares_short  = safe(info.get("sharesShort"))
    shares_float  = safe(info.get("floatShares"))
    short_ratio   = safe(info.get("shortRatio"))
    inst_own      = safe(info.get("heldPercentInstitutions"))
    target_mean   = safe(info.get("targetMeanPrice"))
    target_high   = safe(info.get("targetHighPrice"))
    target_low    = safe(info.get("targetLowPrice"))
    analyst_count = safe(info.get("numberOfAnalystOpinions"))
    eps_fwd       = safe(info.get("epsForward"))
    eps_curr      = safe(info.get("epsCurrentYear"))

    # Derived
    ebitda_margin  = round(ebitda / total_rev * 100, 1)      if ebitda and total_rev else None
    fcf_margin     = round(free_cf / total_rev * 100, 1)     if free_cf and total_rev else None
    fcf_yield      = round(free_cf / market_cap * 100, 2)    if free_cf and market_cap else None
    fcf_conversion = round(free_cf / net_income * 100, 1)    if free_cf and net_income and net_income > 0 else None
    net_debt       = (total_debt - total_cash)                if total_debt and total_cash else None
    net_debt_ebitda= round(net_debt / ebitda, 2)             if net_debt and ebitda and ebitda > 0 else None
    pfcf           = round(price_now / (free_cf / shares_out), 2) if free_cf and shares_out and free_cf > 0 else None
    short_pct      = round(shares_short / shares_float * 100, 2)  if shares_short and shares_float else None
    accruals_ratio = round((net_income - op_cashflow) / total_assets * 100, 2) if net_income and op_cashflow and total_assets and total_assets > 0 else None
    upside_pct     = round((target_mean / price_now - 1) * 100, 1) if target_mean else None

    # Analyst recs
    analyst_recs_str = "N/A"
    strong_buy = buy_n = hold_n = sell_n = strong_sell = 0
    try:
        recs = t.recommendations_summary
        if recs is not None and not recs.empty:
            row = recs.iloc[0]
            strong_buy  = int(row.get("strongBuy",  0))
            buy_n       = int(row.get("buy",        0))
            hold_n      = int(row.get("hold",       0))
            sell_n      = int(row.get("sell",       0))
            strong_sell = int(row.get("strongSell", 0))
            analyst_recs_str = f"Strong Buy: {strong_buy}, Buy: {buy_n}, Hold: {hold_n}, Sell: {sell_n}, Strong Sell: {strong_sell}"
    except Exception:
        pass

    # Next earnings
    next_earnings = "N/A"
    try:
        dates = t.earnings_dates
        if dates is not None and not dates.empty:
            upcoming = dates[dates.index > pd.Timestamp.now(tz="UTC")]
            if not upcoming.empty:
                next_earnings = upcoming.index[0].strftime("%Y-%m-%d")
    except Exception:
        pass

    def pct(v):  return f"{round(v * 100, 1)}%" if v is not None else "N/A"
    def num(v, d=2): return f"{round(v, d)}" if v is not None else "N/A"
    def bn(v):   return f"${v / 1e9:.2f}B" if v is not None else "N/A"
    def pos(v):  return f"+{v}" if v and v > 0 else str(v) if v is not None else "N/A"

    # ── Determine overall rating from signals ────────────────────────────────
    bullish = sum([
        1 if price_now > ma50  else 0,
        1 if price_now > ma200 else 0,
        1 if ma50 > ma200      else 0,
        1 if (rsi_val and 40 < rsi_val < 70) else 0,
        1 if (macd_val and signal_val and macd_val > signal_val) else 0,
        1 if (strong_buy + buy_n > hold_n + sell_n + strong_sell) else 0,
    ])
    if bullish >= 5:
        rating_class, rating_text = "badge-green", "BUY"
    elif bullish >= 3:
        rating_class, rating_text = "badge-amber", "NEUTRAL"
    else:
        rating_class, rating_text = "badge-red",   "SELL"

    ma_class   = "badge-green" if ma50 > ma200 else "badge-red"
    ma_label   = "Golden Cross" if ma50 > ma200 else "Death Cross"
    rsi_class  = "badge-red" if (rsi_val and rsi_val > 70) else "badge-amber" if (rsi_val and rsi_val < 40) else "badge-green"
    rsi_label  = "Overbought" if (rsi_val and rsi_val > 70) else "Oversold" if (rsi_val and rsi_val < 30) else "Neutral"
    macd_class = "badge-green" if (macd_val and signal_val and macd_val > signal_val) else "badge-red"
    macd_label = "Bullish" if (macd_val and signal_val and macd_val > signal_val) else "Bearish"
    w52_class  = "badge-green" if (pct_52w and pct_52w > 85) else "badge-amber" if (pct_52w and pct_52w > 70) else "badge-red"

    def margin_badge(val, high, low):
        if val is None: return "badge-amber", "N/A"
        v = val * 100
        if v >= high: return "badge-green", f"{v:.1f}%"
        if v >= low:  return "badge-amber", f"{v:.1f}%"
        return "badge-red", f"{v:.1f}%"

    gm_cls,  gm_val  = margin_badge(gross_margin, 40, 20)
    opm_cls, opm_val = margin_badge(op_margin,    15, 5)
    npm_cls, npm_val = margin_badge(net_margin,   10, 0)

    report_date = pd.Timestamp.now().strftime("%B %d, %Y")

    # ── Python-generated header HTML (always accurate, no AI) ────────────────
    header_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{ticker} — Equity Research</title>
<style>{REPORT_CSS}</style>
</head>
<body>

<h1>{info.get('longName', ticker)}</h1>
<p class="meta">{ticker} &nbsp;|&nbsp; {info.get('sector','N/A')} — {info.get('industry','N/A')} &nbsp;|&nbsp; {report_date}</p>

<div class="badges">
  <span class="badge {rating_class}">{rating_text}</span>
  <span class="badge badge-blue">Next earnings: {next_earnings}</span>
  <span class="badge {ma_class}">{ma_label}</span>
</div>

<div class="card-grid">
  <div class="card"><div class="card-label">Current price</div><div class="card-value">${round(price_now, 2)}</div><div class="card-sub">{'Daily change: ' + pos(round((price_now/float(info.get("previousClose",price_now))-1)*100,2)) + '%' if info.get('previousClose') else ''}</div></div>
  <div class="card"><div class="card-label">1-year return</div><div class="card-value">{pos(yr_return)}%</div><div class="card-sub">vs S&P 500 RS 6M: {pos(rs_6m)}%</div></div>
  <div class="card"><div class="card-label">Market cap</div><div class="card-value">{bn(market_cap)}</div><div class="card-sub">Revenue TTM: {bn(total_rev)}</div></div>
  <div class="card"><div class="card-label">P/E (forward)</div><div class="card-value">{num(pe_forward)}</div><div class="card-sub">Trailing P/E: {num(pe_trailing)}</div></div>
  <div class="card"><div class="card-label">EV / EBITDA</div><div class="card-value">{num(ev_ebitda)}</div><div class="card-sub">EV/Revenue: {num(ev_revenue)}</div></div>
  <div class="card"><div class="card-label">Free cash flow</div><div class="card-value">{bn(free_cf)}</div><div class="card-sub">FCF yield: {f'{fcf_yield}%' if fcf_yield else 'N/A'}</div></div>
</div>

<div class="section">
<div class="section-title">Key Metrics at a Glance</div>
<table>
  <tr><th>Profitability</th><th>Value</th><th>Signal</th><th>Balance Sheet</th><th>Value</th></tr>
  <tr><td>Gross Margin</td><td>{gm_val}</td><td><span class="badge {gm_cls}">{'Above' if gross_margin and gross_margin*100>=40 else 'Below'} benchmark</span></td><td>Debt / Equity</td><td>{num(debt_eq)}</td></tr>
  <tr><td>Operating Margin</td><td>{opm_val}</td><td><span class="badge {opm_cls}">{'Above' if op_margin and op_margin*100>=15 else 'Below'} benchmark</span></td><td>Net Debt / EBITDA</td><td>{num(net_debt_ebitda)}</td></tr>
  <tr><td>Net Margin</td><td>{npm_val}</td><td><span class="badge {npm_cls}">{'Above' if net_margin and net_margin*100>=10 else 'Below'} benchmark</span></td><td>Current Ratio</td><td>{num(current_ratio)}</td></tr>
  <tr><td>ROE</td><td>{pct(roe)}</td><td><span class="badge {'badge-green' if roe and roe*100>=15 else 'badge-amber'}">{'Strong' if roe and roe*100>=15 else 'Weak'}</span></td><td>Cash</td><td>{bn(total_cash)}</td></tr>
  <tr><td>Revenue Growth (YoY)</td><td>{pct(rev_growth)}</td><td><span class="badge {'badge-green' if rev_growth and rev_growth*100>=10 else 'badge-red'}">{'Growing' if rev_growth and rev_growth>0 else 'Declining'}</span></td><td>Total Debt</td><td>{bn(total_debt)}</td></tr>
  <tr><td>EPS Growth (YoY)</td><td>{pct(eps_growth)}</td><td><span class="badge {'badge-green' if eps_growth and eps_growth*100>=10 else 'badge-amber'}">{'Growing' if eps_growth and eps_growth>0 else 'Declining'}</span></td><td>FCF Conversion</td><td>{f'{fcf_conversion}%' if fcf_conversion else 'N/A'}</td></tr>
  <tr><td>Accruals Ratio</td><td>{f'{accruals_ratio}%' if accruals_ratio is not None else 'N/A'}</td><td><span class="badge {'badge-green' if accruals_ratio is not None and accruals_ratio < 0 else 'badge-red'}">{'Quality signal' if accruals_ratio is not None and accruals_ratio < 0 else 'Watch'}</span></td><td>Inst. Ownership</td><td>{f'{round(inst_own*100,1)}%' if inst_own else 'N/A'}</td></tr>
</table>
</div>

<div class="section">
<div class="section-title">Technical Snapshot</div>
<table>
  <tr><th>Indicator</th><th>Value</th><th>Signal</th><th>Level</th><th>Price vs</th></tr>
  <tr><td>RSI (14-day)</td><td>{num(rsi_val)}</td><td><span class="badge {rsi_class}">{rsi_label}</span></td><td>50-Day MA</td><td>${round(ma50,2)} — <span class="badge {'badge-green' if price_now>ma50 else 'badge-red'}">{'Above' if price_now>ma50 else 'Below'}</span></td></tr>
  <tr><td>MACD</td><td>{num(macd_val)}</td><td><span class="badge {macd_class}">{macd_label} crossover</span></td><td>100-Day MA</td><td>${round(ma100,2)} — <span class="badge {'badge-green' if price_now>ma100 else 'badge-red'}">{'Above' if price_now>ma100 else 'Below'}</span></td></tr>
  <tr><td>52W High proximity</td><td>{f'{pct_52w}%' if pct_52w else 'N/A'}</td><td><span class="badge {w52_class}">{'Positive >85%' if pct_52w and pct_52w>85 else 'Neutral 70-85%' if pct_52w and pct_52w>70 else 'Negative <70%'}</span></td><td>200-Day MA</td><td>${round(ma200,2)} — <span class="badge {'badge-green' if price_now>ma200 else 'badge-red'}">{'Above' if price_now>ma200 else 'Below'}</span></td></tr>
  <tr><td>Volume vs 20D avg</td><td>{f'{vol_ratio}x' if vol_ratio else 'N/A'}</td><td><span class="badge {'badge-green' if vol_ratio and vol_ratio>1.5 else 'badge-amber' if vol_ratio and vol_ratio>0.8 else 'badge-red'}">{'High' if vol_ratio and vol_ratio>1.5 else 'Normal' if vol_ratio and vol_ratio>0.8 else 'Low'}</span></td><td>52W High / Low</td><td>${round(week52_high,2)} / ${round(week52_low,2)}</td></tr>
  <tr><td>RS vs S&P (3M / 6M)</td><td>{pos(rs_3m)}% / {pos(rs_6m)}%</td><td><span class="badge {'badge-green' if rs_6m and rs_6m>0 else 'badge-red'}">{'Outperforming' if rs_6m and rs_6m>0 else 'Underperforming'}</span></td><td>MA Structure</td><td><span class="badge {ma_class}">{ma_label}</span></td></tr>
</table>
</div>

<div class="section">
<div class="section-title">Valuation Multiples</div>
<table>
  <tr><th>Multiple</th><th>Current</th><th>5-Year Avg (est.)</th><th>Sector Median (est.)</th><th>Assessment</th></tr>
  <tr><td>P/E (Forward)</td><td>{num(pe_forward)}</td><td>—</td><td>—</td><td></td></tr>
  <tr><td>EV/EBITDA</td><td>{num(ev_ebitda)}</td><td>—</td><td>—</td><td></td></tr>
  <tr><td>EV/Sales</td><td>{num(ev_revenue)}</td><td>—</td><td>—</td><td></td></tr>
  <tr><td>P/FCF</td><td>{num(pfcf)}</td><td>—</td><td>—</td><td></td></tr>
  <tr><td>PEG Ratio</td><td>{num(peg_ratio)}</td><td>—</td><td>—</td><td></td></tr>
</table>
<p style="font-size:12px;color:#9ca3af;margin-top:4px;">Analyst targets — Mean: ${num(target_mean)} ({pos(upside_pct)}% upside) &nbsp;|&nbsp; High: ${num(target_high)} &nbsp;|&nbsp; Low: ${num(target_low)} &nbsp;|&nbsp; {analyst_count or 'N/A'} analysts &nbsp;|&nbsp; {analyst_recs_str}</p>
</div>

"""

    # ── Ollama prompt: generate analysis sections as HTML ────────────────────
    prompt = f"""You are an institutional equity research analyst. Write a hedge-fund-style equity research report on {ticker} ({info.get('longName', ticker)}) in HTML format.

LIVE DATA (use these exact numbers — do not invent different figures):
Price: ${round(price_now,2)} | Market Cap: {bn(market_cap)} | Sector: {info.get('sector','N/A')} | Industry: {info.get('industry','N/A')}
Revenue TTM: {bn(total_rev)} | EBITDA: {bn(ebitda)} | Net Income: {bn(net_income)} | FCF: {bn(free_cf)}
Revenue Growth: {pct(rev_growth)} | EPS Growth: {pct(eps_growth)} | ROE: {pct(roe)} | ROA: {pct(roa)}
Gross Margin: {pct(gross_margin)} | Op Margin: {pct(op_margin)} | Net Margin: {pct(net_margin)}
P/E Fwd: {num(pe_forward)} | EV/EBITDA: {num(ev_ebitda)} | EV/Rev: {num(ev_revenue)} | PEG: {num(peg_ratio)} | P/FCF: {num(pfcf)}
Debt/Equity: {num(debt_eq)} | Net Debt/EBITDA: {num(net_debt_ebitda)} | Current Ratio: {num(current_ratio)}
FCF Conversion: {f'{fcf_conversion}%' if fcf_conversion else 'N/A'} | Accruals Ratio: {f'{accruals_ratio}%' if accruals_ratio is not None else 'N/A'}
RSI: {num(rsi_val)} | MACD: {macd_label} | MA Structure: {ma_label} | 52W High proximity: {f'{pct_52w}%' if pct_52w else 'N/A'}
Short Interest: {f'{short_pct}%' if short_pct else 'N/A'} | DTC: {num(short_ratio)} | Inst. Ownership: {f'{round(inst_own*100,1)}%' if inst_own else 'N/A'}
Analyst consensus: {analyst_recs_str} | Price target mean: ${num(target_mean)} ({pos(upside_pct)}% upside)
Next earnings: {next_earnings} | EPS current year: {num(eps_curr)} | EPS forward: {num(eps_fwd)}
Beta: {num(beta)} | Total Debt: {bn(total_debt)} | Cash: {bn(total_cash)} | Shares: {f'{shares_out/1e9:.2f}B' if shares_out else 'N/A'}

AVAILABLE CSS CLASSES (use these exactly as shown):
- Sections: <div class="section"><div class="section-title">Title</div>...</div>
- Subsections: <div class="sub-title">SUBTITLE</div>
- White cards: <div class="raised"><strong>Title</strong><p>...</p></div>
- Two columns: <div class="row"><div class="raised">...</div><div class="raised">...</div></div>
- Badges (inline): <span class="badge badge-green">text</span> or badge-amber or badge-red or badge-blue
- Verdict boxes: <div class="verdict v-green"><strong>Title</strong><p>...</p></div> (or v-amber, v-red)
- Warning box: <div class="flag"><strong>⚠ Warning</strong><p>...</p></div>
- Risk items: <div class="risk-item risk-high"><strong>Risk</strong><p>...</p></div> (or risk-med, risk-low)
- Opportunity: <div class="opt"><strong>Opportunity</strong><p>...</p></div>
- Final box: <div class="final"><h2>RATING</h2><p>Conviction: X/10</p><p><em>One-liner thesis</em></p></div>
- Monitoring list: <ul class="check"><li>metric — threshold</li></ul>
- Tables: standard <table><tr><th>/<td> with badge spans inside cells

Write ONLY HTML body content (no <html>, <head>, <style>, or <body> tags).
Be direct and opinionated. Use the badge classes to colour-code every verdict.
Follow this exact structure:

Part 0 — Macro Regime (growth/rate/risk-appetite verdicts with badge colours)
Part 1 — Business & Fundamentals (business model, profitability score /10, ROIC/WACC estimate, cash flow quality, quality acceleration verdict)
Part 2 — Competitive Moat (table with moat sources + evidence, moat rating badge, widening/narrowing verdict)
Part 2B — Stewardship & Management (capital allocation, governance, track record)
Part 3 — Earnings Quality & Estimates (beat/miss history, estimate revision trend, guidance style)
Part 4B — Asymmetry Check (downside floor, upside ceiling, asymmetry ratio, free optionality)
Part 5 — Institutional Flow
  REQUIRED: Open with a .card-grid containing exactly these four cards using the numbers from LIVE DATA:
    Card 1 — "Analyst consensus" showing the buy/hold/sell breakdown and total analysts
    Card 2 — "Avg price target" showing the mean target vs current price (above/below)
    Card 3 — "Short interest" showing short % of float and DTC (days to cover)
    Card 4 — "Institutional ownership" showing the % held by institutions
  Then a .raised block: identify {ticker}'s single closest publicly-traded competitor (by business model, not just sector). Write a balanced 2–3 paragraph comparison covering: leverage/debt structure, valuation multiple, business model differentiation, and which is the better risk-adjusted choice right now with a reason. Use badge colours for verdicts.
  Then comment on any notable strategic investors, major recent index inclusions, or insider activity worth flagging.
  Close with one verdict box on overall institutional sentiment.
Part 6 — Technical Analysis (trend table, 52W high signal, key support/resistance, chart pattern)
Part 7 — Trade Plan (entry zone, stop-loss, target 1, target 2, risk:reward ratio — all in specific $ figures)
Part 8 — Catalysts & Roadmap (near/medium/long term, strategic partnerships)
Part 8B — Market Narrative (current narrative, implied assumptions at current price)
Part 8C — Risks & Monitoring (3 ranked risks as risk-item divs, thesis breakers, monitoring checklist as ul.check)
Part 9 — Conviction Scorecard (HTML table with all 11 factors scored, weighted total, final verdict box)
Bull/Base/Bear scenario table"""

    footer_html = """
<p style="font-size:11px; color:var(--r-sub); margin-top:24px; padding-top:12px; border-top:1px solid var(--r-border);">
This report is for educational and informational purposes only and does not constitute investment advice.
Data sourced from yfinance. AI analysis generated by Groq / llama-3.3-70b — verify all figures independently. DYOR.
</p>
</body></html>"""

    def stream_html_report():
        # 1. Send Python-generated header immediately
        yield f"data: {json.dumps({'text': header_html})}\n\n"

        # 2. Stream Groq analysis (OpenAI-compatible SSE format)
        try:
            with httpx.stream(
                "POST",
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": True,
                    "temperature": 0.3,
                    "max_tokens": 8192,
                },
                timeout=120,
            ) as resp:
                if resp.status_code != 200:
                    body = resp.read().decode()
                    yield f"data: {json.dumps({'text': '<p style=color:red>Groq error ' + str(resp.status_code) + ': ' + body[:200] + '</p>'})}\n\n"
                else:
                    for line in resp.iter_lines():
                        if not line or not line.startswith("data: "):
                            continue
                        payload = line[6:]
                        if payload == "[DONE]":
                            break
                        try:
                            chunk = json.loads(payload)
                            text  = chunk["choices"][0]["delta"].get("content", "")
                            if text:
                                yield f"data: {json.dumps({'text': text})}\n\n"
                        except Exception:
                            continue
        except Exception as e:
            err = str(e)
            yield f"data: {json.dumps({'text': '<p style=color:red>Generation error: ' + err + '</p>'})}\n\n"

        # 3. Send footer and signal completion
        yield f"data: {json.dumps({'text': footer_html})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream_html_report(), media_type="text/event-stream")


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
        _timeout_msg = "\n\n[Generation timed out]"
        yield f"data: {json.dumps({'text': _timeout_msg})}\n\n"
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
