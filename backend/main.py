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

    ma50      = float(close.rolling(50).mean().iloc[-1])
    ma200     = float(close.rolling(200).mean().iloc[-1])
    price_now = float(close.iloc[-1])

    # Compute 1D change from historical closes — avoids stale yfinance info dict
    prev_close = float(close.iloc[-2]) if len(close) >= 2 else price_now
    change_1d  = round((price_now / prev_close - 1) * 100, 2) if prev_close else 0

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
    gross_margin  = safe(info.get("grossMargins"))
    op_margin     = safe(info.get("operatingMargins"))
    net_margin    = safe(info.get("profitMargins"))
    rev_growth    = safe(info.get("revenueGrowth"))
    eps_growth    = safe(info.get("earningsGrowth"))
    free_cf       = safe(info.get("freeCashflow"))
    debt_eq       = safe(info.get("debtToEquity"))

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
        "valuation": {
            "peTrailing":  round(safe(info.get("trailingPE")) or 0, 2) or None,
            "peForward":   round(safe(info.get("forwardPE"))  or 0, 2) or None,
            "evEbitda":    round(safe(info.get("enterpriseToEbitda")) or 0, 2) or None,
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
            "debtEquity":   round(debt_eq, 2) if debt_eq else None,
            "freeCashFlow": round(free_cf / 1e9, 2) if free_cf else None,
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
    if hist.empty:
        raise HTTPException(status_code=404, detail="No price history available")

    close = hist["Close"]
    hist.ta.rsi(length=14, append=True)
    hist.ta.macd(append=True)

    rsi_val    = safe(hist["RSI_14"].iloc[-1])        if "RSI_14"       in hist.columns else None
    macd_val   = safe(hist["MACD_12_26_9"].iloc[-1])  if "MACD_12_26_9"  in hist.columns else None
    signal_val = safe(hist["MACDs_12_26_9"].iloc[-1]) if "MACDs_12_26_9" in hist.columns else None

    ma50  = float(close.rolling(50).mean().iloc[-1])
    ma200 = float(close.rolling(200).mean().iloc[-1])
    price_now = float(close.iloc[-1])

    week52_high    = float(close.rolling(252).max().iloc[-1])
    week52_low     = float(close.rolling(252).min().iloc[-1])
    pct_of_52w_high = round((price_now / week52_high) * 100, 1) if week52_high else None

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
    ev_revenue   = safe(info.get("enterpriseToRevenue"))
    market_cap   = safe(info.get("marketCap"))
    beta         = safe(info.get("beta"))
    total_rev    = safe(info.get("totalRevenue"))
    ebitda       = safe(info.get("ebitda"))
    net_income   = safe(info.get("netIncomeToCommon"))
    total_debt   = safe(info.get("totalDebt"))
    total_cash   = safe(info.get("totalCash"))
    op_cashflow  = safe(info.get("operatingCashflow"))
    shares_out   = safe(info.get("sharesOutstanding"))
    shares_short = safe(info.get("sharesShort"))
    shares_float = safe(info.get("floatShares"))
    short_ratio  = safe(info.get("shortRatio"))
    inst_own     = safe(info.get("heldPercentInstitutions"))
    target_mean  = safe(info.get("targetMeanPrice"))
    target_high  = safe(info.get("targetHighPrice"))
    target_low   = safe(info.get("targetLowPrice"))
    analyst_count = safe(info.get("numberOfAnalystOpinions"))

    short_pct     = round((shares_short / shares_float) * 100, 2) if shares_short and shares_float else None
    fcf_conversion = round((free_cf / net_income) * 100, 1) if free_cf and net_income and net_income > 0 else None
    total_assets  = safe(info.get("totalAssets"))
    accruals_ratio = round((net_income - op_cashflow) / total_assets * 100, 2) if net_income and op_cashflow and total_assets and total_assets > 0 else None
    upside        = f"{round((target_mean / price_now - 1) * 100, 1)}%" if target_mean else "N/A"

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
    def bn(v): return f"${v / 1e9:.2f}B" if v is not None else "N/A"

    prompt = f"""You are an institutional equity research analyst. Produce a hedge fund-style equity research report on {ticker} ({info.get('longName', ticker)}) that answers: **will this stock outperform the S&P 500 over the next 1-18 months without taking on disproportionate risk?**

Do not hedge every sentence. Be direct and opinionated. This report is for an investor with $10,000 to deploy who needs a clear, justified conclusion.

═══ LIVE MARKET DATA — USE AS YOUR PRIMARY SOURCE ═══
Company: {info.get('longName', ticker)}
Sector: {info.get('sector', 'N/A')} | Industry: {info.get('industry', 'N/A')}
Current Price: ${round(price_now, 2)} | Market Cap: {bn(market_cap)}
52-Week High: ${round(week52_high, 2)} | 52-Week Low: ${round(week52_low, 2)} | Price as % of 52W High: {f"{pct_of_52w_high}%" if pct_of_52w_high else "N/A"}

VALUATION:
P/E Trailing: {num(pe_trailing)} | P/E Forward: {num(pe_forward)} | EV/EBITDA: {num(ev_ebitda)} | EV/Revenue: {num(ev_revenue)}

INCOME STATEMENT (TTM):
Revenue: {bn(total_rev)} | EBITDA: {bn(ebitda)} | Net Income: {bn(net_income)}
Revenue Growth (YoY): {pct(rev_growth)} | EPS Growth (YoY): {pct(eps_growth)}
Gross Margin: {pct(gross_margin)} | Operating Margin: {pct(op_margin)} | Net Margin: {pct(net_margin)} | ROE: {pct(roe)}

BALANCE SHEET & CASH FLOW:
Total Debt: {bn(total_debt)} | Cash: {bn(total_cash)} | Debt/Equity: {num(debt_eq)}
Free Cash Flow: {bn(free_cf)} | Operating Cash Flow: {bn(op_cashflow)}
FCF Conversion (FCF/Net Income): {f"{fcf_conversion}%" if fcf_conversion else "N/A"}
Accruals Ratio: {f"{accruals_ratio}%" if accruals_ratio is not None else "N/A"} (negative = quality signal, positive = red flag)
Beta: {num(beta)} | Shares Outstanding: {f"{shares_out/1e9:.2f}B" if shares_out else "N/A"}

TECHNICALS:
RSI (14): {num(rsi_val)} ({'Overbought' if rsi_val and rsi_val > 70 else 'Oversold' if rsi_val and rsi_val < 30 else 'Neutral'})
MACD: {num(macd_val)} | Signal: {num(signal_val)} → {'Bullish' if macd_val and signal_val and macd_val > signal_val else 'Bearish'} crossover
50-Day MA: ${round(ma50, 2)} ({'above' if price_now > ma50 else 'below'}) | 200-Day MA: ${round(ma200, 2)} ({'above' if price_now > ma200 else 'below'})
Golden Cross: {'Yes (50DMA > 200DMA — bullish)' if ma50 > ma200 else 'No (Death Cross — bearish)'}
Volume: {vol_today/1e6:.1f}M ({f"{vol_ratio}x 20-day avg" if vol_ratio else "N/A"})

INSTITUTIONAL & SENTIMENT:
Institutional Ownership: {f"{round(inst_own*100,1)}%" if inst_own else "N/A"}
Short Interest: {f"{short_pct}% of float" if short_pct else "N/A"} | Days-to-Cover: {num(short_ratio)}
Analyst Count: {analyst_count or "N/A"} | Recommendations: {analyst_recs_str}
Price Targets — Mean: ${num(target_mean)}, High: ${num(target_high)}, Low: ${num(target_low)} | Upside to Mean: {upside}
═══════════════════════════════════════════════════════

For data points not in the live data above (e.g. ROIC, PMI, credit spreads, VIX, insider transactions, earnings beat history), use your training knowledge and clearly note when estimating vs citing live data.

# PART 0 — MACRO REGIME CLASSIFICATION

**A. Growth regime** — GDP trend, PMI signal, business cycle stage
Verdict: Growth Expanding | Growth Peaking | Growth Contracting

**B. Inflation & rate regime** — Inflation vs 2% target, Fed stance, yield curve direction
Verdict: Rates Rising | Rates Falling | Rates Stable

**C. Risk appetite** — Credit spreads, VIX level, risk-on vs risk-off flows
Verdict: Risk-On | Risk-Off | Transitioning

**D. Regime implication for {ticker}** — Does the macro regime favour or work against this stock's sector and factor profile? Which factors are rewarded right now?

---

# PART 1 — BUSINESS & FUNDAMENTAL ANALYSIS

## Business Overview
Business model, revenue streams, market share trajectory, pricing power.

## Fundamental Quality Score

### Profitability (weight: 25%)
Analyse gross/operating/net margin trends vs benchmarks (Gross >40%, Op >15%, Net >10%). Flag every miss.

### Capital Efficiency — CORE METRIC (weight: 25%)
Estimate ROIC and WACC. State the ROIC/WACC spread:
- Spread >5%: exceptional compounder | 2-5%: solid | <2%: marginal | Negative: value destruction

### Cash Flow Quality (weight: 20%)
FCF consistency, accruals ratio (from live data above), FCF conversion rate, FCF yield.

### Balance Sheet Strength (weight: 15%)
Net debt/EBITDA, interest coverage, current ratio, covenant risks.

### Quality Acceleration (weight: 15%)
Is ROIC improving or declining? Gross margin trend? FCF conversion trend?
Verdict: Quality Accelerating | Quality Stable | Quality Deteriorating

**FUNDAMENTAL QUALITY SCORE: X/10** — justify and flag the 2 biggest fundamental risks.

---

# PART 2 — COMPETITIVE MOAT
Rate: Weak / Moderate / Strong / Exceptional

| Moat Source | Present? | Evidence |
|---|---|---|
| Brand power | Y/N | |
| Network effects | Y/N | |
| Switching costs | Y/N | |
| Cost advantages | Y/N | |
| IP / patents | Y/N | |
| Regulatory barriers | Y/N | |

Is the moat widening or narrowing?

---

# PART 2B — STEWARDSHIP & MANAGEMENT QUALITY

**Capital Allocation:** How has management deployed cash? Buyback quality (buying cheap or expensive)? M&A track record?
Verdict: Excellent / Good / Mixed / Poor

**Governance:** Compensation structure (revenue vs ROIC/FCF-linked?), CEO tenure, founder-led, board independence, red flags.

**Track Record:** Delivered on past guidance? Behaviour in downturns?
Verdict: High confidence / Neutral / Concern about management

---

# PART 3 — EARNINGS QUALITY & ANALYST EXPECTATIONS

**Earnings Surprise History:** Last 4 quarters beat/miss pattern and average surprise magnitude.

**Estimate Revision Trend:** Direction of EPS revisions last 90 days: UP / DOWN / FLAT. Are more analysts upgrading or downgrading? (Rising revisions = systematic outperformance signal.)

**Management Guidance:** Last guidance: raised / lowered / maintained? Conservative or aggressive style?

---

# PART 4 — VALUATION

## Multiple-Based Relative Valuation
| Multiple | Current | 5-Year Avg | Sector Median | Assessment |
|---|---|---|---|---|
| P/E (forward) | | | | |
| EV/EBITDA | | | | |
| EV/Sales | | | | |
| P/FCF | | | | |
| PEG ratio | | | | |

## DCF — Simplified 5-Year Model
State WACC, revenue CAGR, terminal growth assumptions clearly. Show FCF projection. Sensitivity table:

| Scenario | Revenue CAGR | Terminal Growth | WACC | Intrinsic Value |
|---|---|---|---|---|
| Bear | | | | |
| Base | | | | |
| Bull | | | | |

Verdict: Undervalued / Fairly Valued / Overvalued — with % upside/downside to base intrinsic value.

---

# PART 4B — ASYMMETRY CHECK

**Downside Floor:** Worst realistic outcome and % downside from current price.
**Upside Ceiling:** Best realistic outcome and % upside. What catalyst unlocks it?
**Asymmetry Ratio:** State "For every 1% of downside, there is X% of upside." Minimum 3x threshold.
**Optionality:** Any free call option not priced in (new market, AI integration, pipeline)?

Verdict: Asymmetric (favourable) / Symmetric (neutral) / Negatively skewed (avoid)

---

# PART 5 — INSTITUTIONAL FLOW & POSITIONING

- Institutional ownership: {f"{round(inst_own*100,1)}%" if inst_own else "N/A (estimate)"}
- Short interest: {f"{short_pct}% of float" if short_pct else "N/A (estimate)"} | Days-to-Cover: {num(short_ratio)} (DTC >10 = significant bearish conviction; <3 = low)
- Recent 13F changes: net buying or selling by institutions?
- Insider activity last 6 months (open-market purchases are the signal; grants are noise)
- ETF concentration risk

---

# PART 6 — TECHNICAL ANALYSIS

### Trend Structure
| Timeframe | Trend | Evidence |
|---|---|---|
| Monthly | Bullish/Bearish/Neutral | |
| Weekly | Bullish/Bearish/Neutral | |
| Daily | Bullish/Bearish/Neutral | |

### 52-Week High Proximity
Price is at {f"{pct_of_52w_high}%" if pct_of_52w_high else "N/A"} of 52W high.
Signal: {">85% = Positive momentum" if pct_of_52w_high and pct_of_52w_high > 85 else "70-85% = Neutral" if pct_of_52w_high and pct_of_52w_high > 70 else "<70% = Negative"} (George & Hwang, 2004: 52W high proximity dominates raw price momentum)

### Moving Averages & Momentum
50DMA: ${round(ma50,2)} | 200DMA: ${round(ma200,2)} | Structure: {'Golden Cross (bullish)' if ma50 > ma200 else 'Death Cross (bearish)'}
RSI: {num(rsi_val)} | MACD: {'Bullish crossover' if macd_val and signal_val and macd_val > signal_val else 'Bearish crossover'}
Relative strength vs S&P 500 over 3 and 6 months? Volume trend (accumulation or distribution)?

### Key Levels
Major support and resistance levels. Active chart pattern if any. High-risk (extended) or low-risk (base) setup?

---

# PART 7 — TRADE PLAN

**Ideal entry zone:** $X – $Y (justify: near support, post-pullback, breakout, etc.)
**Stop-loss:** $Z (below key support — where the thesis is wrong)
**Target 1 (1–3 months):** $A
**Target 2 (6–12 months):** $B
**Risk-to-reward:** State ratio. Minimum 2.5:1 medium-term, 3:1 longer-term.

---

# PART 8 — CATALYSTS & ROADMAP

**Near-Term (0–6 months):** Next earnings date, key metrics to watch, product launches, regulatory decisions. For each: positive outcome / negative outcome / base case.

**Medium-Term (6–18 months):** Thesis validation milestones, estimate revision cycle, index inclusion potential.

**Long-Term (2–5 years):** TAM and realistic capture %, revenue/margin destination in bull case, emerging business lines.

**Strategic Partnerships & Backlog:** Named deals, government contracts, major partnerships — is the market pricing these in?

---

# PART 8B — MARKET NARRATIVE & IMPLIED ASSUMPTIONS

**Current narrative** (one sentence): What story does the market believe about this company?
**Narrative lifecycle:** Early adoption (cheap) / Peak hype (expensive) / Narrative fatigue (opportunity)?

**Market-implied assumptions:** At the current P/E and EV/EBITDA, what revenue growth and margins is the market pricing in? Are those assumptions realistic, too optimistic, or too pessimistic?

State explicitly: "For this price to be correct, the market is assuming X% revenue growth and Y% margins. Based on our analysis, this is [realistic/too optimistic/too pessimistic] because..."

**Early stress signals:** Any signs the narrative is weakening?

---

# PART 8C — RISKS, THESIS BREAKERS & MONITORING

**Key Risks** (rank by severity — state impact and whether priced in):
1. [Highest severity] — Impact: / Priced in: Y/N
2. [Second] — Impact: / Priced in: Y/N
3. [Third] — Impact: / Priced in: Y/N

**Thesis Breakers** — 3 specific events that mean exit immediately (e.g. "Two consecutive quarters of gross margin below 40%"):

**Early Warning Indicators** — 5 measurable monthly signals with thresholds:
- [ ] Metric 1 — threshold:
- [ ] Metric 2 — threshold:
- [ ] Metric 3 — threshold:
- [ ] Metric 4 — threshold:
- [ ] Metric 5 — threshold:

**90-Day Checkpoints:**
- Fundamental: [e.g. did revenue growth accelerate?]
- Technical: [e.g. holding above 50DMA on pullbacks?]
- Narrative: [e.g. are analyst estimates moving up or down?]
Decision rule: if 2 of 3 fail, re-evaluate sizing. If all 3 fail, exit.

---

# PART 9 — CONVICTION SCORE & FINAL VERDICT

## Factor Scorecard
| Factor | Score (1–10) | Weight | Weighted Score |
|---|---|---|---|
| Macro regime alignment | /10 | 10% | |
| Fundamental quality & margins | /10 | 15% | |
| ROIC/WACC spread | /10 | 10% | |
| Earnings quality & accruals | /10 | 5% | |
| Estimate revision trend | /10 | 10% | |
| Asymmetry (upside/downside ratio) | /10 | 10% | |
| Moat strength & direction | /10 | 10% | |
| Stewardship & management | /10 | 10% | |
| Market narrative & implied assumptions | /10 | 5% | |
| Technical setup | /10 | 10% | |
| Institutional flow & short interest | /10 | 5% | |
| **TOTAL CONVICTION SCORE** | | 100% | **/10** |

## Final Verdict

1. Can {ticker} beat the S&P 500 over 12–18 months? Yes / No / Uncertain — and why.
2. Primary driver of outperformance?
3. What would make this thesis wrong? (Single most important risk)
4. Is current price a good entry? Yes / No / Wait for pullback

| Scenario | Probability | 12-Month Price Target | Key Assumption |
|---|---|---|---|
| Bull | % | $ | |
| Base | % | $ | |
| Bear | % | $ | |

**STRONG BUY / BUY / NEUTRAL / SELL / STRONG SELL**
**Conviction Score: X/10**
*One-sentence investment thesis:*"""

    def stream_report():
        with httpx.stream(
            "POST",
            "http://localhost:11434/api/chat",
            json={
                "model": "llama3.2",
                "messages": [{"role": "user", "content": prompt}],
                "stream": True,
            },
            timeout=300,
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
    close     = hist["Close"]
    ma50      = float(close.rolling(50).mean().iloc[-1])
    ma200     = float(close.rolling(200).mean().iloc[-1])
    price_now = float(close.iloc[-1])

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
    close = hist["Close"]
    hist.ta.rsi(length=14, append=True)
    hist.ta.macd(append=True)

    rsi_val    = safe(hist["RSI_14"].iloc[-1])        if "RSI_14"       in hist.columns else None
    macd_val   = safe(hist["MACD_12_26_9"].iloc[-1])  if "MACD_12_26_9"  in hist.columns else None
    signal_val = safe(hist["MACDs_12_26_9"].iloc[-1]) if "MACDs_12_26_9" in hist.columns else None
    ma50       = float(close.rolling(50).mean().iloc[-1])
    ma200      = float(close.rolling(200).mean().iloc[-1])
    price_now  = float(close.iloc[-1])

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
        "price":          round(float(t.history(period="1d")["Close"].iloc[-1]), 2),
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
        price_now = float(hist["Close"].iloc[-1])

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

        price      = round(float(t.history(period="1d")["Close"].iloc[-1]), 2)
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

        price = round(float(t.history(period="1d")["Close"].iloc[-1]), 2)

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
        close     = hist["Close"]
        hist.ta.rsi(length=14, append=True)
        hist.ta.macd(append=True)

        price_now  = float(close.iloc[-1])
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
