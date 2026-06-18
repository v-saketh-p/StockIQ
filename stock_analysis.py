import yfinance as yf
import pandas as pd
import pandas_ta as ta

TICKER = "AAPL"

# ANSI colors
G  = "\033[92m"   # green
R  = "\033[91m"   # red
Y  = "\033[93m"   # yellow
B  = "\033[94m"   # blue
W  = "\033[97m"   # white
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"

W_TOTAL = 58


def fmt(val, fmt_str=".2f", suffix=""):
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "N/A"
    try:
        return f"{val:{fmt_str}}{suffix}"
    except (TypeError, ValueError):
        return "N/A"


def colored(val, text, good_if_positive=True):
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return f"{DIM}{text}{RESET}"
    color = (G if val >= 0 else R) if good_if_positive else (R if val >= 0 else G)
    return f"{color}{text}{RESET}"


def header(ticker_name, price, company_name=""):
    top    = f"╔{'═' * (W_TOTAL - 2)}╗"
    bottom = f"╚{'═' * (W_TOTAL - 2)}╝"
    label  = f"  {BOLD}{W}{ticker_name}{RESET}  {DIM}{company_name}{RESET}"
    price_str = f"{BOLD}{G}${price}{RESET}"
    inner  = f"║  {label:<50}  {price_str}  ║"
    print(top)
    title_line = f"  {BOLD}{W}{ticker_name}{RESET}  {DIM}{company_name}{RESET}"
    price_line = f"{BOLD}{G}${price}{RESET}"
    content = f"{title_line}   {price_line}"
    print(f"║  {ticker_name}  {company_name}")
    print(bottom)


def section(title):
    bar = f"{'─' * (W_TOTAL - 2)}"
    print(f"\n  {BOLD}{B}{title}{RESET}")
    print(f"  {DIM}{bar}{RESET}")


def row(label, value, note=""):
    note_str = f"  {DIM}{note}{RESET}" if note else ""
    print(f"  {DIM}{label:<24}{RESET}  {W}{value}{RESET}{note_str}")


def divider():
    print(f"  {DIM}{'·' * 40}{RESET}")


def main():
    print(f"\n{DIM}Fetching data for {TICKER}...{RESET}")
    ticker = yf.Ticker(TICKER)
    info = ticker.info

    name = info.get("longName", "")
    current_price = info.get("currentPrice") or info.get("regularMarketPrice")
    pe_ratio = info.get("trailingPE")
    forward_pe = info.get("forwardPE")
    ev_ebitda = info.get("enterpriseToEbitda")
    roe = info.get("returnOnEquity")
    gross_margin = info.get("grossMargins")
    operating_margin = info.get("operatingMargins")
    net_margin = info.get("profitMargins")
    revenue_growth = info.get("revenueGrowth")
    eps_growth = info.get("earningsGrowth")
    debt_equity = info.get("debtToEquity")
    free_cash_flow = info.get("freeCashflow")

    # ── Header ──────────────────────────────────────────
    print(f"\n  {BOLD}{W}{TICKER}{RESET}  {DIM}{name}{RESET}   {BOLD}{G}${fmt(current_price)}{RESET}")
    print(f"  {DIM}{'─' * 54}{RESET}")

    # ── Valuation ───────────────────────────────────────
    section("VALUATION")
    row("P/E  (trailing)",  fmt(pe_ratio))
    row("P/E  (forward)",   fmt(forward_pe))
    row("EV / EBITDA",      fmt(ev_ebitda))

    # ── Profitability ───────────────────────────────────
    section("PROFITABILITY")
    roe_pct  = roe * 100  if roe              else None
    gm_pct   = gross_margin * 100   if gross_margin   else None
    om_pct   = operating_margin * 100 if operating_margin else None
    nm_pct   = net_margin * 100     if net_margin     else None
    rev_pct  = revenue_growth * 100 if revenue_growth else None
    eps_pct  = eps_growth * 100     if eps_growth     else None

    row("Return on Equity",   colored(roe_pct,  fmt(roe_pct,  suffix="%")))
    row("Gross Margin",       colored(gm_pct,   fmt(gm_pct,   suffix="%")))
    row("Operating Margin",   colored(om_pct,   fmt(om_pct,   suffix="%")))
    row("Net Margin",         colored(nm_pct,   fmt(nm_pct,   suffix="%")))
    divider()
    row("Revenue Growth YoY", colored(rev_pct,  fmt(rev_pct,  suffix="%")))
    row("EPS Growth",         colored(eps_pct,  fmt(eps_pct,  suffix="%")))

    # ── Balance Sheet ───────────────────────────────────
    section("BALANCE SHEET")
    fcf_str = f"${fmt(free_cash_flow / 1e9)}B" if free_cash_flow else "N/A"
    row("Debt / Equity",  colored(debt_equity, fmt(debt_equity), good_if_positive=False))
    row("Free Cash Flow", f"{G}{fcf_str}{RESET}" if free_cash_flow else "N/A")

    # ── Technicals ──────────────────────────────────────
    section("TECHNICALS  (1-year daily)")

    hist = ticker.history(period="1y")
    if hist.empty:
        print(f"  {R}No price history available.{RESET}")
        return

    close = hist["Close"]

    hist.ta.rsi(length=14, append=True)
    rsi_val = hist["RSI_14"].iloc[-1] if "RSI_14" in hist.columns else None

    hist.ta.macd(append=True)
    macd_val   = hist["MACD_12_26_9"].iloc[-1]  if "MACD_12_26_9"  in hist.columns else None
    signal_val = hist["MACDs_12_26_9"].iloc[-1] if "MACDs_12_26_9" in hist.columns else None

    # VWAP (cumulative from start of history window)
    hist.ta.vwap(append=True)
    vwap_col = [c for c in hist.columns if c.startswith("VWAP")]
    vwap_val = hist[vwap_col[0]].iloc[-1] if vwap_col else None

    # Volume
    vol_today  = hist["Volume"].iloc[-1]
    vol_avg20  = hist["Volume"].rolling(20).mean().iloc[-1]

    ma50      = close.rolling(50).mean().iloc[-1]
    ma200     = close.rolling(200).mean().iloc[-1]
    price_now = close.iloc[-1]

    # RSI color: green 30-70, red outside
    if rsi_val is not None:
        if rsi_val > 70:
            rsi_color, rsi_note = R, "overbought"
        elif rsi_val < 30:
            rsi_color, rsi_note = G, "oversold"
        else:
            rsi_color, rsi_note = G, "neutral"
        rsi_str = f"{rsi_color}{fmt(rsi_val)}{RESET}"
    else:
        rsi_str, rsi_note = "N/A", ""

    # MACD
    if macd_val is not None and signal_val is not None:
        bull = macd_val > signal_val
        mc   = G if bull else R
        macd_str  = f"{mc}{fmt(macd_val)}{RESET}"
        sig_str   = f"{fmt(signal_val)}"
        trend_str = f"{mc}{'Bullish ↑' if bull else 'Bearish ↓'}{RESET}"
    else:
        macd_str = sig_str = trend_str = "N/A"

    # VWAP display
    if vwap_val is not None and not pd.isna(vwap_val):
        above_vwap = price_now > vwap_val
        vwap_str  = f"${fmt(vwap_val)}"
        vwap_note = f"{G if above_vwap else R}{'↑ above' if above_vwap else '↓ below'} price{RESET}"
    else:
        vwap_str, vwap_note = "N/A", ""

    # Volume display
    vol_ratio = vol_today / vol_avg20 if vol_avg20 else None
    vol_color = G if (vol_ratio or 0) >= 1 else DIM
    vol_str   = f"{vol_color}{vol_today / 1e6:.1f}M{RESET}"
    vol_note  = f"avg {vol_avg20 / 1e6:.1f}M  {vol_color}{fmt(vol_ratio, '.2f')}x avg{RESET}" if vol_ratio else ""

    row("RSI (14)",   rsi_str,  note=rsi_note)
    row("MACD",       macd_str, note=f"signal {sig_str}  {trend_str}")
    row("VWAP",       vwap_str, note=vwap_note)
    row("Volume",     vol_str,  note=vol_note)
    divider()
    above50  = price_now > ma50
    above200 = price_now > ma200
    row("50-Day MA",  f"${fmt(ma50)}",  note=f"{G if above50  else R}{'↑ above' if above50  else '↓ below'} price{RESET}")
    row("200-Day MA", f"${fmt(ma200)}", note=f"{G if above200 else R}{'↑ above' if above200 else '↓ below'} price{RESET}")

    print()


if __name__ == "__main__":
    main()
