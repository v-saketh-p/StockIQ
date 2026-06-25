import yfinance as yf

for sym in ['NVDA', 'AAPL', 'META', 'JNJ', 'VZ']:
    t = yf.Ticker(sym)
    info = t.info
    hist = t.history(period='5d')
    hist = hist[hist['Close'].notna()]
    price = float(hist['Close'].iloc[-1]) if not hist.empty else None

    div_rate          = info.get('dividendRate')
    trailing_rate     = info.get('trailingAnnualDividendRate')
    last_div_value    = info.get('lastDividendValue')
    last_div_date     = info.get('lastDividendDate')
    five_yr_avg_yield = info.get('fiveYearAvgDividendYield')

    calc_from_rate     = round((div_rate / price) * 100, 4) if (div_rate and price) else None
    calc_from_trailing = round((trailing_rate / price) * 100, 4) if (trailing_rate and price) else None
    calc_from_last_div = round((last_div_value * 4 / price) * 100, 4) if (last_div_value and price) else None

    print(f"{sym}  price={round(price,2) if price else None}")
    print(f"  dividendRate:              {div_rate}  -> yield: {calc_from_rate}%")
    print(f"  trailingAnnualDivRate:     {trailing_rate}  -> yield: {calc_from_trailing}%")
    print(f"  lastDividendValue:         {last_div_value}  -> annualised yield: {calc_from_last_div}%")
    print(f"  lastDividendDate:          {last_div_date}")
    print(f"  fiveYearAvgDividendYield:  {five_yr_avg_yield}%  (already in %)")
    print()
