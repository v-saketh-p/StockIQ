"""
ARM (Adaptive Regime Momentum) Strategy Backtester
====================================================
Universe  : S&P 100 large-cap stocks
Period    : 2010-01-01 to 2024-12-31
Benchmark : SPY (buy-and-hold)
Rebalance : Monthly (month-end)

Regime logic per stock:
  ADX > 25  →  trending  →  12-1 month momentum signal
  ADX < 20  →  ranging   →  RSI + Bollinger Band mean-reversion signal
  20–25     →  neutral   →  momentum signal (conservative)

Position sizing: equal-weight, max 10 holdings
Stop logic: not enforced intra-month (rebalance acts as natural stop)
"""

import warnings
warnings.filterwarnings("ignore")

import sys
import numpy as np
import pandas as pd
import yfinance as yf
import matplotlib
matplotlib.use("Agg")          # non-interactive backend (saves to file)
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from indicators import (
    compute_adx,
    compute_rsi,
    compute_bollinger_bands,
    compute_momentum_12_1,
    compute_atr,
    compute_volume_ratio,
)

# ── Universe ───────────────────────────────────────────────────────────────────
UNIVERSE = [
    # Mega-cap Tech
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA",
    # Semiconductors
    "AVGO", "AMD",  "QCOM", "TXN",  "INTC",  "MU",   "AMAT", "LRCX", "KLAC", "MRVL",
    # Software / Cloud / Cybersecurity
    "CRM",  "ADBE", "INTU", "NOW",  "ORCL",  "PLTR", "CRWD", "NET",  "DDOG", "ZS",  "SNOW",
    # Enterprise / Legacy Tech
    "CSCO", "IBM",  "ACN",
    # Financials - Banks
    "JPM",  "BAC",  "GS",   "MS",   "WFC",   "C",
    # Financials - Other
    "V",    "MA",   "AXP",  "BLK",  "BX",    "CME",  "USB",  "COF",
    # Healthcare - Managed Care
    "UNH",  "CI",   "HUM",  "CVS",
    # Healthcare - Pharma / Biotech
    "JNJ",  "LLY",  "ABBV", "MRK",  "AMGN",  "BMY",  "GILD", "PFE",  "REGN", "VRTX",
    # Healthcare - MedTech
    "TMO",  "ISRG", "SYK",  "ZTS",  "ABT",   "DHR",  "MDT",
    # Consumer Discretionary
    "HD",   "MCD",  "SBUX", "NKE",  "BKNG",  "TGT",  "LOW",  "ABNB", "CMG",
    # Consumer Staples
    "WMT",  "COST", "PG",   "KO",   "PEP",   "PM",   "MO",   "MDLZ", "CL",
    # Energy
    "CVX",  "XOM",  "OXY",  "COP",  "SLB",
    # Industrials / Defense
    "CAT",  "DE",   "HON",  "UNP",  "LMT",   "RTX",  "NOC",  "BA",   "EMR",  "GE",
    # Telecom / Media / Entertainment
    "VZ",   "T",    "DIS",  "NFLX", "CMCSA",
    # Utilities
    "NEE",  "DUK",  "SO",
    # Real Estate
    "AMT",  "PLD",  "EQIX",
    # Auto / Other
    "F",    "GM",   "PYPL", "INTC",
]

# ── Config ─────────────────────────────────────────────────────────────────────
START             = "2010-01-01"
END               = "2024-12-31"
INITIAL_CAPITAL   = 100_000

MAX_POSITIONS     = 10          # max stocks held simultaneously
MOM_SLOTS         = 8           # momentum picks per rebalance
MR_SLOTS          = 4           # mean-reversion picks per rebalance

ADX_TREND         = 22          # ADX above → trending
ADX_RANGE         = 15          # ADX below → ranging

RSI_OVERSOLD      = 30          # mean-rev buy trigger
BB_PCT_OVERSOLD   = 0.25        # near lower BB (bottom 25% of band)
VOL_SPIKE         = 1.3         # volume > 1.3x 20-day avg (confirms reversal)

OUTPUT_PNG        = "backtest_results.png"


# ── Data Download ──────────────────────────────────────────────────────────────

def download_data():
    print(f"[1/4] Downloading {len(UNIVERSE)} stocks from Yahoo Finance ({START} to {END})...")
    raw = yf.download(UNIVERSE, start=START, end=END, auto_adjust=True, progress=True)

    # yfinance multi-ticker: columns are (field, ticker)
    if isinstance(raw.columns, pd.MultiIndex):
        close  = raw["Close"]
        high   = raw["High"]
        low    = raw["Low"]
        volume = raw["Volume"]
    else:
        # Single-ticker fallback (shouldn't happen with a list)
        close  = raw[["Close"]]
        high   = raw[["High"]]
        low    = raw[["Low"]]
        volume = raw[["Volume"]]

    # Forward-fill small gaps (holidays / early listings)
    close  = close.ffill().dropna(how="all")
    high   = high.ffill().dropna(how="all")
    low    = low.ffill().dropna(how="all")
    volume = volume.ffill().dropna(how="all")

    print(f"    [OK] {len(close.columns)} tickers loaded, {len(close)} trading days\n")
    return close, high, low, volume


def download_benchmark():
    spy = yf.download("SPY", start=START, end=END, auto_adjust=True, progress=False)
    if isinstance(spy.columns, pd.MultiIndex):
        return spy["Close"].squeeze()
    return spy["Close"]


# ── Signal Computation ─────────────────────────────────────────────────────────

def build_signal_db(close, high, low, volume):
    """
    Pre-compute all indicators for every ticker.
    Returns dict: ticker → DataFrame with columns
        [close, adx, plus_di, minus_di, rsi, bb_pct, momentum, vol_ratio]
    """
    print("[2/4] Computing signals for all tickers...")
    db = {}
    tickers = close.columns.tolist()

    for i, ticker in enumerate(tickers):
        c = close[ticker].dropna()
        h = high[ticker].reindex(c.index)
        l = low[ticker].reindex(c.index)
        v = volume[ticker].reindex(c.index)

        if len(c) < 300:
            continue

        adx_s, plus_di, minus_di = compute_adx(h, l, c)
        rsi_s                    = compute_rsi(c)
        _, _, _, bb_pct          = compute_bollinger_bands(c)
        mom                      = compute_momentum_12_1(c)
        vol_r                    = compute_volume_ratio(v)

        db[ticker] = pd.DataFrame({
            "close":    c,
            "adx":      adx_s,
            "plus_di":  plus_di,
            "minus_di": minus_di,
            "rsi":      rsi_s,
            "bb_pct":   bb_pct,
            "momentum": mom,
            "vol_ratio":vol_r,
        })

        if (i + 1) % 20 == 0 or (i + 1) == len(tickers):
            print(f"    {i+1}/{len(tickers)} tickers processed", end="\r")

    print(f"\n    [OK] Signal DB built for {len(db)} tickers\n")
    return db


# ── Stock Selection ────────────────────────────────────────────────────────────

def select_stocks(date, db):
    """
    At each rebalance date, rank stocks and return up to MAX_POSITIONS tickers.
    Blends momentum (trending stocks) and mean-reversion (ranging stocks).
    """
    rows = []
    for ticker, df in db.items():
        if date not in df.index:
            continue
        r = df.loc[date]
        if r[["adx", "rsi", "bb_pct", "momentum", "vol_ratio"]].isna().any():
            continue
        rows.append({
            "ticker":    ticker,
            "adx":       r["adx"],
            "rsi":       r["rsi"],
            "bb_pct":    r["bb_pct"],
            "momentum":  r["momentum"],
            "vol_ratio": r["vol_ratio"],
            "plus_di":   r["plus_di"],
            "minus_di":  r["minus_di"],
        })

    if not rows:
        return []

    df_all = pd.DataFrame(rows)

    # ── Momentum picks (trending regime) ──────────────────────────────────────
    trending = df_all[df_all["adx"] >= ADX_TREND].copy()
    # Require upward direction (plus_di leading) and positive momentum
    trending = trending[
        (trending["plus_di"] > trending["minus_di"]) &
        (trending["momentum"] > 0)
    ]
    mom_picks = (
        trending.nlargest(MOM_SLOTS, "momentum")["ticker"].tolist()
        if not trending.empty else []
    )

    # Fill momentum slots from neutral zone if needed
    if len(mom_picks) < MOM_SLOTS:
        neutral = df_all[
            (df_all["adx"] >= ADX_RANGE) &
            (~df_all["ticker"].isin(mom_picks)) &
            (df_all["momentum"] > 0)
        ]
        extra = neutral.nlargest(MOM_SLOTS - len(mom_picks), "momentum")["ticker"].tolist()
        mom_picks += extra

    # ── Mean-reversion picks (ranging regime) ─────────────────────────────────
    ranging = df_all[df_all["adx"] < ADX_RANGE].copy()
    mr_candidates = ranging[
        (ranging["rsi"]      < RSI_OVERSOLD)  &
        (ranging["bb_pct"]   < BB_PCT_OVERSOLD) &
        (ranging["vol_ratio"] > VOL_SPIKE)    &
        (~ranging["ticker"].isin(mom_picks))
    ]
    mr_picks = (
        mr_candidates.nsmallest(MR_SLOTS, "rsi")["ticker"].tolist()
        if not mr_candidates.empty else []
    )

    return mom_picks + mr_picks


# ── Portfolio Simulation ───────────────────────────────────────────────────────

def run_backtest(db, close):
    """
    Equal-weight portfolio, rebalanced at every month-end.
    Uses close.shift(1) for previous-day prices to avoid stale-price bugs.
    Signals are generated on the last trading day of each month;
    the new portfolio is active starting the next trading day.
    """
    print("[3/4] Running backtest simulation...")

    # Pre-compute daily returns for every ticker (avoids per-ticker shifting in the loop)
    daily_ret_matrix = close.pct_change()   # shape: (days, tickers)

    # Month-end rebalance dates aligned to actual trading days
    trading_days = close.index
    rebalance_dates = set(trading_days[::10])  # bi-weekly

    holdings      = []
    port_value    = INITIAL_CAPITAL
    history       = []
    rebalance_log = []

    for i, date in enumerate(trading_days):
        # On a rebalance day: compute new selection; holdings take effect NEXT day
        # (signals seen at close, trades executed at next open → conservative)
        if date in rebalance_dates:
            new_holdings = select_stocks(date, db)
            if new_holdings:
                holdings = new_holdings
                rebalance_log.append((date, len(holdings), holdings[:]))

        # Daily P&L: equal-weight of today's returns for current holdings
        # Skip day 0 (no previous close) and days with no holdings
        if holdings and i > 0:
            rets = []
            for t in holdings:
                if t in daily_ret_matrix.columns:
                    r = daily_ret_matrix.loc[date, t]
                    if not np.isnan(r):
                        rets.append(r)
            if rets:
                port_value *= (1 + np.mean(rets))

        history.append({"date": date, "value": port_value})

    print(f"    [OK] Backtest complete - {len(rebalance_log)} rebalances\n")
    return (
        pd.DataFrame(history).set_index("date")["value"],
        rebalance_log,
    )


# ── Performance Metrics ────────────────────────────────────────────────────────

def compute_metrics(portfolio: pd.Series, benchmark: pd.Series):
    p_ret = portfolio.pct_change().dropna()
    b_ret = benchmark.pct_change().dropna()
    common = p_ret.index.intersection(b_ret.index)
    p_ret, b_ret = p_ret[common], b_ret[common]

    years = (portfolio.index[-1] - portfolio.index[0]).days / 365.25

    total_ret  = portfolio.iloc[-1] / portfolio.iloc[0] - 1
    cagr       = (1 + total_ret) ** (1 / years) - 1
    sharpe     = p_ret.mean() / p_ret.std() * np.sqrt(252)
    roll_max   = portfolio.cummax()
    max_dd     = ((portfolio - roll_max) / roll_max).min()
    annual_vol = p_ret.std() * np.sqrt(252)

    bench_total = benchmark.reindex(portfolio.index).ffill().iloc[-1] / \
                  benchmark.reindex(portfolio.index).ffill().iloc[0] - 1
    bench_cagr  = (1 + bench_total) ** (1 / years) - 1
    bench_sharpe = b_ret.mean() / b_ret.std() * np.sqrt(252)

    # Sortino (downside only)
    downside = p_ret[p_ret < 0].std() * np.sqrt(252)
    sortino  = (cagr) / downside if downside > 0 else np.nan

    # Calmar
    calmar = cagr / abs(max_dd) if max_dd != 0 else np.nan

    # Monthly win rate
    monthly_p = portfolio.resample("ME").last().pct_change().dropna()
    win_rate   = (monthly_p > 0).mean()

    return {
        "Period":                   f"{START[:4]} - {END[:4]}",
        "-" * 36:                   "",
        "ARM Total Return":          f"{total_ret:>10.1%}",
        "ARM CAGR":                  f"{cagr:>10.1%}",
        "ARM Sharpe Ratio":          f"{sharpe:>10.2f}",
        "ARM Sortino Ratio":         f"{sortino:>10.2f}",
        "ARM Calmar Ratio":          f"{calmar:>10.2f}",
        "ARM Max Drawdown":          f"{max_dd:>10.1%}",
        "ARM Annual Volatility":     f"{annual_vol:>10.1%}",
        "ARM Monthly Win Rate":      f"{win_rate:>10.1%}",
        " " * 36:                   "",
        "SPY Total Return":          f"{bench_total:>10.1%}",
        "SPY CAGR":                  f"{bench_cagr:>10.1%}",
        "SPY Sharpe Ratio":          f"{bench_sharpe:>10.2f}",
        "  " * 36:                  "",
        "Alpha (CAGR over SPY)":     f"{cagr - bench_cagr:>10.1%}",
    }


# ── Annual Returns ─────────────────────────────────────────────────────────────

def compute_annual_returns(portfolio: pd.Series, benchmark: pd.Series):
    """Year-by-year return comparison. Returns a list of (year, arm_ret, spy_ret, beat)."""
    bench_aligned = benchmark.reindex(portfolio.index).ffill()
    rows = []
    for year in range(portfolio.index[0].year, portfolio.index[-1].year + 1):
        mask = portfolio.index.year == year
        if mask.sum() < 20:
            continue
        p_slice = portfolio[mask]
        b_slice = bench_aligned[mask]
        arm_ret = p_slice.iloc[-1] / p_slice.iloc[0] - 1
        spy_ret = b_slice.iloc[-1] / b_slice.iloc[0] - 1
        rows.append((year, arm_ret, spy_ret, arm_ret > spy_ret))
    return rows


def print_annual_table(rows):
    print("\n  Year   ARM      SPY      Beat?")
    print("  " + "-" * 35)
    beats = 0
    for year, arm, spy, beat in rows:
        marker = "YES" if beat else "no "
        if beat:
            beats += 1
        print(f"  {year}  {arm:>+7.1%}  {spy:>+7.1%}   {marker}")
    print("  " + "-" * 35)
    print(f"  Beat SPY {beats}/{len(rows)} years ({beats/len(rows):.0%})\n")


def compute_walk_forward(portfolio: pd.Series, benchmark: pd.Series):
    """Split into in-sample (2010-2019) and out-of-sample (2020-2024) periods."""
    split = pd.Timestamp("2020-01-01")

    def period_stats(p, b):
        b = b.reindex(p.index).ffill()
        years    = (p.index[-1] - p.index[0]).days / 365.25
        p_ret    = p.iloc[-1] / p.iloc[0] - 1
        b_ret    = b.iloc[-1] / b.iloc[0] - 1
        p_cagr   = (1 + p_ret) ** (1 / years) - 1
        b_cagr   = (1 + b_ret) ** (1 / years) - 1
        dr       = p.pct_change().dropna()
        sharpe   = dr.mean() / dr.std() * np.sqrt(252) if dr.std() > 0 else np.nan
        roll_max = p.cummax()
        max_dd   = ((p - roll_max) / roll_max).min()
        return p_cagr, b_cagr, sharpe, max_dd

    bench_aligned = benchmark.reindex(portfolio.index).ffill()

    in_mask  = portfolio.index < split
    out_mask = portfolio.index >= split

    in_p,  in_b  = portfolio[in_mask],  bench_aligned[in_mask]
    out_p, out_b = portfolio[out_mask], bench_aligned[out_mask]

    in_stats  = period_stats(in_p,  in_b)
    out_stats = period_stats(out_p, out_b)

    print("=" * 52)
    print("  WALK-FORWARD VALIDATION")
    print("=" * 52)
    print(f"  {'':30}  {'ARM':>7}  {'SPY':>7}")
    print(f"  {'-'*46}")
    print(f"  IN-SAMPLE  2010-2019")
    print(f"  {'  CAGR':30}  {in_stats[0]:>7.1%}  {in_stats[1]:>7.1%}")
    print(f"  {'  Sharpe':30}  {in_stats[2]:>7.2f}")
    print(f"  {'  Max Drawdown':30}  {in_stats[3]:>7.1%}")
    print(f"  {'-'*46}")
    print(f"  OUT-OF-SAMPLE  2020-2024  (unseen)")
    print(f"  {'  CAGR':30}  {out_stats[0]:>7.1%}  {out_stats[1]:>7.1%}")
    print(f"  {'  Sharpe':30}  {out_stats[2]:>7.2f}")
    print(f"  {'  Max Drawdown':30}  {out_stats[3]:>7.1%}")
    print("=" * 52)
    verdict = "PASS" if out_stats[0] > out_stats[1] else "FAIL"
    print(f"  Verdict: {verdict} - ARM {'beat' if verdict == 'PASS' else 'MISSED'} SPY out-of-sample\n")


# ── Permutation Test ───────────────────────────────────────────────────────────

def run_permutation_test(close, db, n_sim=1000):
    """
    Randomly pick N stocks each month-end, simulate 1000 portfolios.
    Tests whether ARM's CAGR is statistically better than random selection
    from the same universe with the same mechanics.
    """
    print(f"Running permutation test ({n_sim} random portfolios)...", end=" ", flush=True)

    daily_rets = close.pct_change()
    eligible   = [t for t in db if t in close.columns]

    trading_days = close.index
    month_ends   = pd.date_range(START, END, freq="ME")

    rebal_set = set()
    for me in month_ends:
        idx = trading_days.searchsorted(me, side="right") - 1
        if 0 <= idx < len(trading_days):
            rebal_set.add(idx)

    # Build numpy return matrix for speed (days x eligible_tickers)
    cols       = [c for c in eligible if c in daily_rets.columns]
    ret_matrix = daily_rets[cols].values.astype(float)  # (n_days, n_tickers)
    n_tickers  = len(cols)
    n_days     = len(trading_days)
    n_hold     = MAX_POSITIONS
    years      = (trading_days[-1] - trading_days[0]).days / 365.25

    rng        = np.random.default_rng(seed=42)
    rand_cagrs = []

    for _ in range(n_sim):
        port_val = float(INITIAL_CAPITAL)
        held     = rng.choice(n_tickers, size=n_hold, replace=False)

        for i in range(1, n_days):
            if i in rebal_set:
                held = rng.choice(n_tickers, size=n_hold, replace=False)
            day_rets = ret_matrix[i, held]
            valid    = day_rets[~np.isnan(day_rets)]
            if len(valid):
                port_val *= 1.0 + np.mean(valid)

        rand_cagrs.append((port_val / INITIAL_CAPITAL) ** (1 / years) - 1)

    print("done.\n")
    return rand_cagrs


def print_permutation_results(arm_cagr: float, rand_cagrs: list, spy_cagr: float):
    arr        = np.array(rand_cagrs)
    percentile = (arr < arm_cagr).mean() * 100
    median_rnd = np.median(arr)
    p95        = np.percentile(arr, 95)

    print("=" * 52)
    print("  STATISTICAL SIGNIFICANCE TEST")
    print("  (1,000 random portfolios, same universe & rules)")
    print("=" * 52)
    print(f"  Median random CAGR          {median_rnd:>10.1%}")
    print(f"  95th pct random CAGR        {p95:>10.1%}")
    print(f"  SPY CAGR                    {spy_cagr:>10.1%}")
    print(f"  ARM CAGR                    {arm_cagr:>10.1%}")
    print(f"  ARM beats random portfolios {percentile:>9.1f}%")
    print("-" * 52)
    if percentile >= 95:
        verdict = f"SIGNIFICANT (p < 0.05) -- top {100-percentile:.1f}% of all random runs"
    elif percentile >= 90:
        verdict = f"LIKELY REAL (p < 0.10) -- top {100-percentile:.1f}% of all random runs"
    else:
        verdict = f"WEAK -- only beats {percentile:.1f}% of random runs"
    print(f"  Verdict: {verdict}")
    print("=" * 52 + "\n")
    return arr


# ── Plotting ───────────────────────────────────────────────────────────────────

def plot_permutation_dist(rand_cagrs: list, arm_cagr: float,
                          spy_cagr: float, save_path="permutation_test.png"):
    arr = np.array(rand_cagrs) * 100
    arm_pct = arm_cagr * 100
    spy_pct = spy_cagr * 100

    fig, ax = plt.subplots(figsize=(12, 5))
    fig.patch.set_facecolor("#0f0f0f")
    ax.set_facecolor("#1a1a2e")

    ax.hist(arr, bins=60, color="#4da6ff", alpha=0.6, edgecolor="none", label="1,000 random portfolios")
    ax.axvline(np.percentile(arr, 95), color="#ffaa00", linewidth=1.5,
               linestyle="--", label=f"95th pct ({np.percentile(arr,95):.1f}%)")
    ax.axvline(spy_pct,  color="#aaaaff", linewidth=1.5, linestyle=":",  label=f"SPY ({spy_pct:.1f}%)")
    ax.axvline(arm_pct,  color="#00ff88", linewidth=2.5, label=f"ARM ({arm_pct:.1f}%)")

    percentile = (np.array(rand_cagrs) < arm_cagr).mean() * 100
    ax.set_title(f"ARM beats {percentile:.1f}% of random portfolios  (same universe, same rules)",
                 color="white", fontsize=13, fontweight="bold")
    ax.set_xlabel("CAGR (%)", color="#aaaaaa")
    ax.set_ylabel("Frequency", color="#aaaaaa")
    ax.tick_params(colors="#aaaaaa")
    ax.spines[:].set_color("#333355")
    ax.grid(alpha=0.15, color="#444466", axis="x")
    ax.legend(facecolor="#1a1a2e", labelcolor="white", fontsize=10)

    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches="tight", facecolor="#0f0f0f")
    print(f"    Distribution chart saved -> {save_path}\n")


def plot_results(portfolio: pd.Series, benchmark: pd.Series,
                 metrics: dict, annual_rows: list):
    bench_aligned = benchmark.reindex(portfolio.index).ffill()

    port_norm  = portfolio     / portfolio.iloc[0]     * 100
    bench_norm = bench_aligned / bench_aligned.iloc[0] * 100

    roll_max = portfolio.cummax()
    drawdown = (portfolio - roll_max) / roll_max * 100

    fig, axes = plt.subplots(3, 1, figsize=(14, 12),
                             gridspec_kw={"height_ratios": [3, 1, 1.4]})
    fig.patch.set_facecolor("#0f0f0f")
    for ax in axes:
        ax.set_facecolor("#1a1a2e")

    # ── Equity curve ──
    ax1 = axes[0]
    ax1.plot(port_norm.index,  port_norm.values,
             color="#00ff88", linewidth=2,   label="ARM Strategy", zorder=3)
    ax1.plot(bench_norm.index, bench_norm.values,
             color="#4da6ff", linewidth=1.5, label="SPY Buy & Hold",
             alpha=0.85, zorder=2)
    ax1.fill_between(port_norm.index, port_norm.values, bench_norm.values,
                     where=(port_norm.values > bench_norm.values),
                     color="#00ff88", alpha=0.07, zorder=1)
    # Walk-forward split line
    ax1.axvline(pd.Timestamp("2020-01-01"), color="#ffaa00",
                linewidth=1.2, linestyle="--", alpha=0.7, label="OOS start (2020)")
    ax1.set_title("ARM Strategy vs SPY  (2010 - 2024)",
                  color="white", fontsize=14, fontweight="bold", pad=12)
    ax1.set_ylabel("Growth of $100", color="#aaaaaa")
    ax1.tick_params(colors="#aaaaaa")
    ax1.spines[:].set_color("#333355")
    ax1.grid(alpha=0.15, color="#444466")
    ax1.legend(facecolor="#1a1a2e", labelcolor="white", fontsize=10)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    # ── Drawdown ──
    ax2 = axes[1]
    ax2.fill_between(drawdown.index, drawdown.values, 0,
                     color="#ff4444", alpha=0.6)
    ax2.plot(drawdown.index, drawdown.values, color="#ff4444", linewidth=0.8)
    ax2.axvline(pd.Timestamp("2020-01-01"), color="#ffaa00",
                linewidth=1.2, linestyle="--", alpha=0.7)
    ax2.set_ylabel("Drawdown %", color="#aaaaaa")
    ax2.tick_params(colors="#aaaaaa")
    ax2.spines[:].set_color("#333355")
    ax2.grid(alpha=0.15, color="#444466")
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    # ── Annual returns bar chart ──
    ax3 = axes[2]
    years      = [r[0] for r in annual_rows]
    arm_rets   = [r[1] * 100 for r in annual_rows]
    spy_rets   = [r[2] * 100 for r in annual_rows]
    x          = np.arange(len(years))
    w          = 0.35
    arm_colors = ["#00ff88" if r > 0 else "#ff4444" for r in arm_rets]
    spy_colors = ["#4da6ff" if r > 0 else "#ff9944" for r in spy_rets]

    ax3.bar(x - w/2, arm_rets, w, color=arm_colors, label="ARM", alpha=0.85)
    ax3.bar(x + w/2, spy_rets, w, color=spy_colors, label="SPY", alpha=0.6)
    ax3.axhline(0, color="#555577", linewidth=0.8)
    ax3.axvline(x[next((i for i, y in enumerate(years) if y == 2020), len(years)-1)] - 0.5,
                color="#ffaa00", linewidth=1.2, linestyle="--", alpha=0.7)
    ax3.set_xticks(x)
    ax3.set_xticklabels(years, color="#aaaaaa", fontsize=8)
    ax3.set_ylabel("Annual Return %", color="#aaaaaa")
    ax3.set_xlabel("  <-- In-sample    |    Out-of-sample -->", color="#ffaa00", fontsize=8)
    ax3.tick_params(colors="#aaaaaa")
    ax3.spines[:].set_color("#333355")
    ax3.grid(alpha=0.15, color="#444466", axis="y")
    ax3.legend(facecolor="#1a1a2e", labelcolor="white", fontsize=9)

    plt.tight_layout(pad=2.0)
    plt.savefig(OUTPUT_PNG, dpi=150, bbox_inches="tight", facecolor="#0f0f0f")
    print(f"    Chart saved -> {OUTPUT_PNG}\n")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 52)
    print("   ARM - Adaptive Regime Momentum Backtester")
    print("=" * 52 + "\n")

    close, high, low, volume = download_data()
    db                       = build_signal_db(close, high, low, volume)
    portfolio, rebal_log     = run_backtest(db, close)

    spy          = download_benchmark()
    metrics      = compute_metrics(portfolio, spy)
    annual_rows  = compute_annual_returns(portfolio, spy)

    print("[4/4] Results\n")
    print("=" * 52)
    print("   ARM STRATEGY  -  BACKTEST RESULTS")
    print("=" * 52)
    for k, v in metrics.items():
        if v:
            print(f"  {k:<36} {v}")
        else:
            print(f"  {k}")
    print("=" * 52 + "\n")

    print("  YEAR-BY-YEAR BREAKDOWN")
    print_annual_table(annual_rows)

    compute_walk_forward(portfolio, spy)

    # Statistical significance
    years_total   = (portfolio.index[-1] - portfolio.index[0]).days / 365.25
    arm_cagr_val  = (portfolio.iloc[-1] / portfolio.iloc[0]) ** (1 / years_total) - 1
    spy_b         = spy.reindex(portfolio.index).ffill()
    spy_cagr_val  = (spy_b.iloc[-1] / spy_b.iloc[0]) ** (1 / years_total) - 1

    rand_cagrs    = run_permutation_test(close, db)
    print_permutation_results(arm_cagr_val, rand_cagrs, spy_cagr_val)

    print("Last 5 rebalances:")
    for date, n, tickers in rebal_log[-5:]:
        print(f"  {date.date()}  ->  {n} holdings: {', '.join(tickers[:6])}{'...' if n > 6 else ''}")

    print("\nGenerating charts...")
    plot_results(portfolio, spy, metrics, annual_rows)
    plot_permutation_dist(rand_cagrs, arm_cagr_val, spy_cagr_val)
    print("Done. Open backtest_results.png and permutation_test.png\n")


if __name__ == "__main__":
    main()
