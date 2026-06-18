import yfinance as yf
import pandas as pd
import pandas_ta as ta

TICKER = "AAPL"


def fmt(val, fmt_str=".2f", suffix=""):
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "N/A"
    try:
        return f"{val:{fmt_str}}{suffix}"
    except (TypeError, ValueError):
        return "N/A"


def print_section(title):
    print(f"\n{'=' * 50}")
    print(f"  {title}")
    print(f"{'=' * 50}")


def print_row(label, value):
    print(f"  {label:<30} {value}")


def main():
    print(f"\nFetching data for: {TICKER}")
    ticker = yf.Ticker(TICKER)
    info = ticker.info

    # --- Fundamentals ---
    print_section("FUNDAMENTALS")

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

    print_row("Current Price", f"${fmt(current_price)}")
    print_row("P/E Ratio (Trailing)", fmt(pe_ratio))
    print_row("P/E Ratio (Forward)", fmt(forward_pe))
    print_row("EV/EBITDA", fmt(ev_ebitda))
    print_row("Return on Equity (ROE)", fmt(roe * 100 if roe else None, ".2f", "%"))
    print_row("Gross Margin", fmt(gross_margin * 100 if gross_margin else None, ".2f", "%"))
    print_row("Operating Margin", fmt(operating_margin * 100 if operating_margin else None, ".2f", "%"))
    print_row("Net Margin", fmt(net_margin * 100 if net_margin else None, ".2f", "%"))
    print_row("Revenue Growth (YoY)", fmt(revenue_growth * 100 if revenue_growth else None, ".2f", "%"))
    print_row("EPS Growth", fmt(eps_growth * 100 if eps_growth else None, ".2f", "%"))
    print_row("Debt / Equity", fmt(debt_equity))
    if free_cash_flow:
        fcf_b = free_cash_flow / 1_000_000_000
        print_row("Free Cash Flow", f"${fmt(fcf_b)}B")
    else:
        print_row("Free Cash Flow", "N/A")

    # --- Technical Indicators ---
    print_section("TECHNICAL INDICATORS (1-Year Daily)")

    hist = ticker.history(period="1y")
    if hist.empty:
        print("  No price history available.")
        return

    close = hist["Close"]

    # RSI
    hist.ta.rsi(length=14, append=True)
    rsi_col = "RSI_14"
    rsi_val = hist[rsi_col].iloc[-1] if rsi_col in hist.columns else None

    # MACD
    hist.ta.macd(append=True)
    macd_col = "MACD_12_26_9"
    macd_signal_col = "MACDs_12_26_9"
    macd_val = hist[macd_col].iloc[-1] if macd_col in hist.columns else None
    macd_signal_val = hist[macd_signal_col].iloc[-1] if macd_signal_col in hist.columns else None

    # Moving Averages
    ma50 = close.rolling(window=50).mean().iloc[-1]
    ma200 = close.rolling(window=200).mean().iloc[-1]
    price_now = close.iloc[-1]

    ma50_pos = "ABOVE" if price_now > ma50 else "BELOW"
    ma200_pos = "ABOVE" if price_now > ma200 else "BELOW"

    macd_signal_str = "N/A"
    if macd_val is not None and macd_signal_val is not None:
        direction = "Bullish (MACD > Signal)" if macd_val > macd_signal_val else "Bearish (MACD < Signal)"
        macd_signal_str = f"{fmt(macd_val)}  |  Signal: {fmt(macd_signal_val)}  |  {direction}"

    print_row("Current Price", f"${fmt(price_now)}")
    print_row("RSI (14)", fmt(rsi_val))
    print_row("MACD", macd_signal_str)
    print_row("50-Day MA", f"${fmt(ma50)}  |  Price is {ma50_pos}")
    print_row("200-Day MA", f"${fmt(ma200)}  |  Price is {ma200_pos}")

    print()


if __name__ == "__main__":
    main()
