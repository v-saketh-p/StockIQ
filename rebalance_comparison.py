"""
ARM Strategy — Rebalancing Frequency Comparison
=================================================
Tests 4 rebalancing frequencies on the same signal logic:
  - Weekly     (~every 5 trading days)
  - Bi-weekly  (~every 10 trading days)
  - Monthly    (month-end)  ← current
  - Quarterly  (quarter-end)

Signals and universe are identical across all four.
Permutation test runs only on the winner to save time.
"""

import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import yfinance as yf
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from indicators import (
    compute_adx, compute_rsi, compute_bollinger_bands,
    compute_momentum_12_1, compute_volume_ratio,
)

# ── Universe & Config ──────────────────────────────────────────────────────────
UNIVERSE = [
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

START           = "2010-01-01"
END             = "2024-12-31"
INITIAL_CAPITAL = 100_000
MAX_POSITIONS   = 10
MOM_SLOTS       = 6
MR_SLOTS        = 4
ADX_TREND       = 25
ADX_RANGE       = 20
RSI_OVERSOLD    = 35
BB_PCT_OVERSOLD = 0.25
VOL_SPIKE       = 1.3
N_PERMS         = 1000


# ── Data Download ──────────────────────────────────────────────────────────────
def download_data():
    print(f"[1/3] Downloading {len(set(UNIVERSE))} stocks...")
    raw = yf.download(list(set(UNIVERSE)), start=START, end=END,
                      auto_adjust=True, progress=True)
    close  = raw["Close"].ffill().dropna(how="all")
    high   = raw["High"].ffill().dropna(how="all")
    low    = raw["Low"].ffill().dropna(how="all")
    volume = raw["Volume"].ffill().dropna(how="all")
    print(f"    [OK] {len(close.columns)} tickers, {len(close)} trading days\n")
    return close, high, low, volume

def download_benchmark():
    spy = yf.download("SPY", start=START, end=END, auto_adjust=True, progress=False)
    return spy["Close"].squeeze() if isinstance(spy.columns, pd.MultiIndex) else spy["Close"]


# ── Signal DB ──────────────────────────────────────────────────────────────────
def build_signal_db(close, high, low, volume):
    print("[2/3] Computing signals...")
    db = {}
    for i, ticker in enumerate(close.columns.tolist()):
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
            "close": c, "adx": adx_s, "plus_di": plus_di, "minus_di": minus_di,
            "rsi": rsi_s, "bb_pct": bb_pct, "momentum": mom, "vol_ratio": vol_r,
        })
        if (i + 1) % 20 == 0 or (i + 1) == len(close.columns):
            print(f"    {i+1}/{len(close.columns)} tickers processed", end="\r")
    print(f"\n    [OK] Signal DB built for {len(db)} tickers\n")
    return db


# ── Stock Selection ────────────────────────────────────────────────────────────
def select_stocks(date, db):
    rows = []
    for ticker, df in db.items():
        if date not in df.index:
            continue
        r = df.loc[date]
        if r[["adx", "rsi", "bb_pct", "momentum", "vol_ratio"]].isna().any():
            continue
        rows.append({
            "ticker": ticker, "adx": r["adx"], "rsi": r["rsi"],
            "bb_pct": r["bb_pct"], "momentum": r["momentum"],
            "vol_ratio": r["vol_ratio"], "plus_di": r["plus_di"], "minus_di": r["minus_di"],
        })
    if not rows:
        return []
    df_all = pd.DataFrame(rows)

    trending = df_all[df_all["adx"] >= ADX_TREND].copy()
    trending = trending[(trending["plus_di"] > trending["minus_di"]) & (trending["momentum"] > 0)]
    mom_picks = trending.nlargest(MOM_SLOTS, "momentum")["ticker"].tolist() if not trending.empty else []

    if len(mom_picks) < MOM_SLOTS:
        neutral = df_all[
            (df_all["adx"] >= ADX_RANGE) &
            (~df_all["ticker"].isin(mom_picks)) &
            (df_all["momentum"] > 0)
        ]
        mom_picks += neutral.nlargest(MOM_SLOTS - len(mom_picks), "momentum")["ticker"].tolist()

    ranging = df_all[df_all["adx"] < ADX_RANGE].copy()
    mr_candidates = ranging[
        (ranging["rsi"] < RSI_OVERSOLD) &
        (ranging["bb_pct"] < BB_PCT_OVERSOLD) &
        (ranging["vol_ratio"] > VOL_SPIKE) &
        (~ranging["ticker"].isin(mom_picks))
    ]
    mr_picks = mr_candidates.nsmallest(MR_SLOTS, "rsi")["ticker"].tolist() if not mr_candidates.empty else []

    return mom_picks + mr_picks


# ── Rebalance Date Builders ────────────────────────────────────────────────────
def get_rebalance_dates(trading_days, freq):
    if freq == "weekly":
        return set(trading_days[::5])
    elif freq == "biweekly":
        return set(trading_days[::10])
    elif freq == "monthly":
        month_ends = pd.date_range(START, END, freq="ME")
        dates = set()
        for me in month_ends:
            idx = trading_days.searchsorted(me, side="right") - 1
            if 0 <= idx < len(trading_days):
                dates.add(trading_days[idx])
        return dates
    elif freq == "quarterly":
        quarter_ends = pd.date_range(START, END, freq="QE")
        dates = set()
        for qe in quarter_ends:
            idx = trading_days.searchsorted(qe, side="right") - 1
            if 0 <= idx < len(trading_days):
                dates.add(trading_days[idx])
        return dates


# ── Backtest Engine ────────────────────────────────────────────────────────────
def run_backtest(db, close, freq):
    daily_ret_matrix = close.pct_change()
    trading_days     = close.index
    rebalance_dates  = get_rebalance_dates(trading_days, freq)

    holdings   = []
    port_value = INITIAL_CAPITAL
    history    = []

    for i, date in enumerate(trading_days):
        if date in rebalance_dates:
            new = select_stocks(date, db)
            if new:
                holdings = new
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

    return pd.DataFrame(history).set_index("date")["value"]


# ── Metrics ────────────────────────────────────────────────────────────────────
def compute_metrics(portfolio, benchmark):
    p_ret = portfolio.pct_change().dropna()
    b_ret = benchmark.pct_change().dropna()
    common = p_ret.index.intersection(b_ret.index)
    p_ret, b_ret = p_ret[common], b_ret[common]

    years      = (portfolio.index[-1] - portfolio.index[0]).days / 365.25
    total_ret  = portfolio.iloc[-1] / portfolio.iloc[0] - 1
    cagr       = (1 + total_ret) ** (1 / years) - 1
    sharpe     = p_ret.mean() / p_ret.std() * np.sqrt(252)
    roll_max   = portfolio.cummax()
    max_dd     = ((portfolio - roll_max) / roll_max).min()
    annual_vol = p_ret.std() * np.sqrt(252)
    downside   = p_ret[p_ret < 0].std() * np.sqrt(252)
    sortino    = cagr / downside if downside > 0 else np.nan

    bench_b    = benchmark.reindex(portfolio.index).ffill()
    bench_ret  = bench_b.iloc[-1] / bench_b.iloc[0] - 1
    bench_cagr = (1 + bench_ret) ** (1 / years) - 1

    monthly_p = portfolio.resample("ME").last().pct_change().dropna()
    win_rate  = (monthly_p > 0).mean()

    # Walk-forward
    split    = pd.Timestamp("2020-01-01")
    in_p     = portfolio[portfolio.index < split]
    out_p    = portfolio[portfolio.index >= split]
    in_b     = bench_b[bench_b.index < split]
    out_b    = bench_b[bench_b.index >= split]

    def period_cagr(p, b):
        y = (p.index[-1] - p.index[0]).days / 365.25
        pc = (p.iloc[-1] / p.iloc[0]) ** (1/y) - 1
        bc = (b.iloc[-1] / b.iloc[0]) ** (1/y) - 1
        return pc, bc

    in_cagr,  in_spy  = period_cagr(in_p,  in_b)
    out_cagr, out_spy = period_cagr(out_p, out_b)

    return {
        "cagr": cagr, "sharpe": sharpe, "sortino": sortino,
        "max_dd": max_dd, "annual_vol": annual_vol, "win_rate": win_rate,
        "alpha": cagr - bench_cagr, "bench_cagr": bench_cagr,
        "in_cagr": in_cagr, "in_spy": in_spy,
        "out_cagr": out_cagr, "out_spy": out_spy,
    }


# ── Permutation Test ───────────────────────────────────────────────────────────
def run_permutation_test(close, db, portfolio, n_sim=N_PERMS):
    print(f"\nRunning permutation test on winner ({n_sim} random portfolios)...", end=" ", flush=True)
    daily_rets = close.pct_change()
    eligible   = [t for t in db if t in close.columns]
    trading_days = close.index
    month_ends   = pd.date_range(START, END, freq="ME")

    rebal_set = set()
    for me in month_ends:
        idx = trading_days.searchsorted(me, side="right") - 1
        if 0 <= idx < len(trading_days):
            rebal_set.add(idx)

    cols       = [c for c in eligible if c in daily_rets.columns]
    ret_matrix = daily_rets[cols].values.astype(float)
    n_tickers  = len(cols)
    n_days     = len(trading_days)
    years      = (trading_days[-1] - trading_days[0]).days / 365.25
    rng        = np.random.default_rng(seed=42)
    rand_cagrs = []

    for _ in range(n_sim):
        port_val = float(INITIAL_CAPITAL)
        held     = rng.choice(n_tickers, size=MAX_POSITIONS, replace=False)
        for i in range(1, n_days):
            if i in rebal_set:
                held = rng.choice(n_tickers, size=MAX_POSITIONS, replace=False)
            day_rets = ret_matrix[i, held]
            valid    = day_rets[~np.isnan(day_rets)]
            if len(valid):
                port_val *= 1.0 + np.mean(valid)
        rand_cagrs.append((port_val / INITIAL_CAPITAL) ** (1 / years) - 1)

    years_total  = (portfolio.index[-1] - portfolio.index[0]).days / 365.25
    arm_cagr     = (portfolio.iloc[-1] / portfolio.iloc[0]) ** (1 / years_total) - 1
    arr          = np.array(rand_cagrs)
    percentile   = (arr < arm_cagr).mean() * 100
    print("done.")
    return percentile, arr, arm_cagr


# ── Plotting ───────────────────────────────────────────────────────────────────
def plot_comparison(portfolios, benchmark, results):
    bench_aligned = benchmark.reindex(list(portfolios.values())[0].index).ffill()

    fig, axes = plt.subplots(2, 1, figsize=(14, 10),
                             gridspec_kw={"height_ratios": [3, 1]})
    fig.patch.set_facecolor("#0f0f0f")
    for ax in axes:
        ax.set_facecolor("#1a1a2e")

    colors = {"weekly": "#ff6b6b", "biweekly": "#ffd93d", "monthly": "#00ff88", "quarterly": "#4da6ff"}
    labels = {"weekly": "Weekly", "biweekly": "Bi-weekly", "monthly": "Monthly (current)", "quarterly": "Quarterly"}

    ax1 = axes[0]
    bench_norm = bench_aligned / bench_aligned.iloc[0] * 100
    ax1.plot(bench_norm.index, bench_norm.values, color="#888888",
             linewidth=1.5, linestyle="--", label="SPY Buy & Hold", alpha=0.7)

    for freq, port in portfolios.items():
        norm = port / port.iloc[0] * 100
        ax1.plot(norm.index, norm.values, color=colors[freq],
                 linewidth=2, label=f"{labels[freq]}  (CAGR {results[freq]['cagr']:.1%}  Sharpe {results[freq]['sharpe']:.2f})")

    ax1.axvline(pd.Timestamp("2020-01-01"), color="#ffaa00",
                linewidth=1.2, linestyle="--", alpha=0.6, label="OOS start (2020)")
    ax1.set_title("ARM Strategy — Rebalancing Frequency Comparison (2010–2024)",
                  color="white", fontsize=13, fontweight="bold")
    ax1.set_ylabel("Growth of $100", color="#aaaaaa")
    ax1.tick_params(colors="#aaaaaa")
    ax1.spines[:].set_color("#333355")
    ax1.grid(alpha=0.15, color="#444466")
    ax1.legend(facecolor="#1a1a2e", labelcolor="white", fontsize=9)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    # Drawdown panel
    ax2 = axes[1]
    for freq, port in portfolios.items():
        roll_max = port.cummax()
        dd = (port - roll_max) / roll_max * 100
        ax2.plot(dd.index, dd.values, color=colors[freq], linewidth=1, label=labels[freq])
    ax2.axvline(pd.Timestamp("2020-01-01"), color="#ffaa00",
                linewidth=1.2, linestyle="--", alpha=0.6)
    ax2.set_ylabel("Drawdown %", color="#aaaaaa")
    ax2.tick_params(colors="#aaaaaa")
    ax2.spines[:].set_color("#333355")
    ax2.grid(alpha=0.15, color="#444466")
    ax2.legend(facecolor="#1a1a2e", labelcolor="white", fontsize=8, ncol=4)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    plt.tight_layout(pad=2.0)
    plt.savefig("rebalance_comparison.png", dpi=150, bbox_inches="tight", facecolor="#0f0f0f")
    print("    Chart saved -> rebalance_comparison.png\n")


def plot_permutation(rand_cagrs, arm_cagr, spy_cagr, freq_label):
    arr     = np.array(rand_cagrs) * 100
    arm_pct = arm_cagr * 100
    spy_pct = spy_cagr * 100

    fig, ax = plt.subplots(figsize=(12, 5))
    fig.patch.set_facecolor("#0f0f0f")
    ax.set_facecolor("#1a1a2e")

    ax.hist(arr, bins=60, color="#4da6ff", alpha=0.6, edgecolor="none", label="1,000 random portfolios")
    ax.axvline(np.percentile(arr, 95), color="#ffaa00", linewidth=1.5,
               linestyle="--", label=f"95th pct ({np.percentile(arr,95):.1f}%)")
    ax.axvline(spy_pct, color="#aaaaff", linewidth=1.5, linestyle=":", label=f"SPY ({spy_pct:.1f}%)")
    ax.axvline(arm_pct, color="#00ff88", linewidth=2.5, label=f"ARM / {freq_label} ({arm_pct:.1f}%)")

    percentile = (np.array(rand_cagrs) < arm_cagr).mean() * 100
    ax.set_title(f"ARM ({freq_label}) beats {percentile:.1f}% of random portfolios",
                 color="white", fontsize=13, fontweight="bold")
    ax.set_xlabel("CAGR (%)", color="#aaaaaa")
    ax.set_ylabel("Frequency", color="#aaaaaa")
    ax.tick_params(colors="#aaaaaa")
    ax.spines[:].set_color("#333355")
    ax.grid(alpha=0.15, color="#444466", axis="x")
    ax.legend(facecolor="#1a1a2e", labelcolor="white", fontsize=10)

    plt.tight_layout()
    plt.savefig("permutation_winner.png", dpi=150, bbox_inches="tight", facecolor="#0f0f0f")
    print("    Permutation chart saved -> permutation_winner.png\n")


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    print("\n" + "=" * 60)
    print("   ARM — Rebalancing Frequency Comparison")
    print("=" * 60 + "\n")

    close, high, low, volume = download_data()
    db  = build_signal_db(close, high, low, volume)
    spy = download_benchmark()

    freqs = ["weekly", "biweekly", "monthly", "quarterly"]
    labels = {"weekly": "Weekly", "biweekly": "Bi-weekly", "monthly": "Monthly", "quarterly": "Quarterly"}

    portfolios = {}
    results    = {}

    print("[3/3] Running backtests for all 4 frequencies...\n")
    for freq in freqs:
        print(f"  Testing {labels[freq]}...", end=" ", flush=True)
        port           = run_backtest(db, close, freq)
        m              = compute_metrics(port, spy)
        portfolios[freq] = port
        results[freq]    = m
        print(f"CAGR {m['cagr']:.1%}  Sharpe {m['sharpe']:.2f}  MaxDD {m['max_dd']:.1%}")

    # ── Results Table ──
    print("\n" + "=" * 72)
    print("   RESULTS SUMMARY")
    print("=" * 72)
    print(f"  {'Metric':<28} {'Weekly':>9} {'Bi-weekly':>10} {'Monthly':>9} {'Quarterly':>10}")
    print("  " + "-" * 68)

    rows = [
        ("CAGR",              "cagr",       "{:.1%}"),
        ("Sharpe Ratio",      "sharpe",     "{:.2f}"),
        ("Sortino Ratio",     "sortino",    "{:.2f}"),
        ("Max Drawdown",      "max_dd",     "{:.1%}"),
        ("Annual Volatility", "annual_vol", "{:.1%}"),
        ("Monthly Win Rate",  "win_rate",   "{:.1%}"),
        ("Alpha over SPY",    "alpha",      "{:.1%}"),
    ]
    for label, key, fmt in rows:
        vals = [fmt.format(results[f][key]) for f in freqs]
        print(f"  {label:<28} {vals[0]:>9} {vals[1]:>10} {vals[2]:>9} {vals[3]:>10}")

    print("  " + "-" * 68)
    print(f"  {'IN-SAMPLE CAGR (2010-19)':<28}", end="")
    for f in freqs:
        print(f" {results[f]['in_cagr']:>9.1%}", end="")
    print()
    print(f"  {'OUT-OF-SAMPLE CAGR (2020-24)':<28}", end="")
    for f in freqs:
        print(f" {results[f]['out_cagr']:>9.1%}", end="")
    print()
    print(f"  {'OOS vs SPY ({:.1%})'.format(results['monthly']['out_spy']):<28}", end="")
    for f in freqs:
        beat = "BEAT" if results[f]['out_cagr'] > results[f]['out_spy'] else "MISS"
        print(f" {beat:>9}", end="")
    print()
    print("=" * 72)

    # Pick winner by Sharpe (risk-adjusted, not just raw return)
    winner = max(results, key=lambda f: results[f]["sharpe"])
    print(f"\n  Winner by Sharpe: {labels[winner].upper()}")
    print(f"  (CAGR {results[winner]['cagr']:.1%}  |  Sharpe {results[winner]['sharpe']:.2f}  |  MaxDD {results[winner]['max_dd']:.1%})\n")

    # Permutation test on winner only
    percentile, rand_cagrs, arm_cagr = run_permutation_test(close, db, portfolios[winner])
    spy_b    = spy.reindex(portfolios[winner].index).ffill()
    spy_cagr = (spy_b.iloc[-1] / spy_b.iloc[0]) ** \
               (1 / ((portfolios[winner].index[-1] - portfolios[winner].index[0]).days / 365.25)) - 1

    print(f"\n  Permutation result ({labels[winner]}): beats {percentile:.1f}% of random portfolios", end=" ")
    if percentile >= 95:
        print(f"-> SIGNIFICANT (p < 0.05)")
    elif percentile >= 90:
        print(f"-> LIKELY REAL (p < 0.10)")
    else:
        print(f"-> WEAK")

    print("\nGenerating charts...")
    plot_comparison(portfolios, spy, results)
    plot_permutation(rand_cagrs, arm_cagr, spy_cagr, labels[winner])
    print("Done. Open rebalance_comparison.png and permutation_winner.png\n")


if __name__ == "__main__":
    main()
