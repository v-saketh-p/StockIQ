"""
ARM Strategy — Parameter Grid Search (Phase 2)
================================================
Approach:
  1. Pre-compute signal DB once (all indicators, full date range)
  2. Grid search 432 parameter combos — evaluated on IN-SAMPLE only (2010-2019)
  3. Rank by in-sample Sharpe ratio
  4. Validate top 10 on OUT-OF-SAMPLE (2020-2024) — untouched data
  5. Run permutation test on the overall winner
  6. Save charts + print full results

Rebalancing: bi-weekly (every 10 trading days) — winner from Phase 1

Fixed parameters (not tuned — enough variables already):
  BB_PCT_OVERSOLD = 0.25
  VOL_SPIKE       = 1.3
  MR_SLOTS        = 4
"""

import warnings
warnings.filterwarnings("ignore")

import itertools
import numpy as np
import pandas as pd
import yfinance as yf
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from dataclasses import dataclass

from indicators import (
    compute_adx, compute_rsi, compute_bollinger_bands,
    compute_momentum_12_1, compute_volume_ratio,
)

# ── Universe ───────────────────────────────────────────────────────────────────
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

# ── Config ─────────────────────────────────────────────────────────────────────
START           = "2010-01-01"
END             = "2024-12-31"
INSAMPLE_END    = "2019-12-31"
OOS_START       = "2020-01-01"
INITIAL_CAPITAL = 100_000
REBAL_FREQ      = 10        # bi-weekly = every 10 trading days
MR_SLOTS        = 4
BB_PCT_OVERSOLD = 0.25
VOL_SPIKE       = 1.3
N_PERMS         = 1000
TOP_N           = 10        # validate top N combos out-of-sample

# ── Parameter Grid ─────────────────────────────────────────────────────────────
ADX_TRENDS   = [22, 25, 28, 30]
ADX_RANGES   = [15, 18, 20]
RSI_LEVELS   = [30, 35, 40]
MOM_MINS     = [0.0, 0.05, 0.10]
MOM_SLOTS_L  = [5, 6, 7, 8]

# Only include combos where ADX range is meaningfully below trend (gap >= 3)
PARAM_GRID = [
    (adx_t, adx_r, rsi, mom_min, mom_slots)
    for adx_t, adx_r, rsi, mom_min, mom_slots
    in itertools.product(ADX_TRENDS, ADX_RANGES, RSI_LEVELS, MOM_MINS, MOM_SLOTS_L)
    if adx_t - adx_r >= 3
]


@dataclass
class Params:
    adx_trend:  int
    adx_range:  int
    rsi_os:     int
    mom_min:    float
    mom_slots:  int

    def label(self):
        return (f"ADX>{self.adx_trend}/<{self.adx_range}  "
                f"RSI<{self.rsi_os}  "
                f"Mom>{self.mom_min:.0%}  "
                f"Slots={self.mom_slots}")


# ── Data ───────────────────────────────────────────────────────────────────────
def download_data():
    print(f"[1/4] Downloading {len(set(UNIVERSE))} stocks...")
    raw    = yf.download(list(set(UNIVERSE)), start=START, end=END,
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
    print("[2/4] Pre-computing signals for all tickers...")
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
            "close": c, "adx": adx_s, "plus_di": plus_di, "minus_di": minus_di,
            "rsi": rsi_s, "bb_pct": bb_pct, "momentum": mom, "vol_ratio": vol_r,
        })
        if (i + 1) % 20 == 0 or (i + 1) == len(tickers):
            print(f"    {i+1}/{len(tickers)} tickers", end="\r")
    print(f"\n    [OK] Signal DB: {len(db)} tickers\n")
    return db


# ── Stock Selection (parameterized) ───────────────────────────────────────────
def select_stocks(date, db, p: Params):
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

    # Momentum picks
    trending = df_all[df_all["adx"] >= p.adx_trend].copy()
    trending = trending[
        (trending["plus_di"] > trending["minus_di"]) &
        (trending["momentum"] >= p.mom_min)
    ]
    mom_picks = trending.nlargest(p.mom_slots, "momentum")["ticker"].tolist() if not trending.empty else []

    if len(mom_picks) < p.mom_slots:
        neutral = df_all[
            (df_all["adx"] >= p.adx_range) &
            (~df_all["ticker"].isin(mom_picks)) &
            (df_all["momentum"] >= p.mom_min)
        ]
        mom_picks += neutral.nlargest(p.mom_slots - len(mom_picks), "momentum")["ticker"].tolist()

    # Mean reversion picks
    ranging = df_all[df_all["adx"] < p.adx_range].copy()
    mr_cands = ranging[
        (ranging["rsi"]      < p.rsi_os)       &
        (ranging["bb_pct"]   < BB_PCT_OVERSOLD) &
        (ranging["vol_ratio"] > VOL_SPIKE)      &
        (~ranging["ticker"].isin(mom_picks))
    ]
    mr_picks = mr_cands.nsmallest(MR_SLOTS, "rsi")["ticker"].tolist() if not mr_cands.empty else []

    return mom_picks + mr_picks


# ── Backtest Engine ────────────────────────────────────────────────────────────
def run_backtest(db, close, p: Params, date_mask=None):
    """
    date_mask: optional boolean Series to restrict to a date range.
    Returns portfolio value Series.
    """
    trading_days     = close.index if date_mask is None else close.index[date_mask]
    daily_ret_matrix = close.pct_change()
    rebal_indices    = set(range(0, len(trading_days), REBAL_FREQ))

    holdings   = []
    port_value = INITIAL_CAPITAL
    history    = []

    for i, date in enumerate(trading_days):
        if i in rebal_indices:
            new = select_stocks(date, db, p)
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
def sharpe(portfolio):
    r = portfolio.pct_change().dropna()
    return r.mean() / r.std() * np.sqrt(252) if r.std() > 0 else 0.0

def full_metrics(portfolio, benchmark):
    p_ret     = portfolio.pct_change().dropna()
    years     = (portfolio.index[-1] - portfolio.index[0]).days / 365.25
    total_ret = portfolio.iloc[-1] / portfolio.iloc[0] - 1
    cagr      = (1 + total_ret) ** (1 / years) - 1
    sh        = p_ret.mean() / p_ret.std() * np.sqrt(252)
    roll_max  = portfolio.cummax()
    max_dd    = ((portfolio - roll_max) / roll_max).min()
    downside  = p_ret[p_ret < 0].std() * np.sqrt(252)
    sortino   = cagr / downside if downside > 0 else np.nan
    bench_b   = benchmark.reindex(portfolio.index).ffill()
    b_years   = (bench_b.index[-1] - bench_b.index[0]).days / 365.25
    b_cagr    = (bench_b.iloc[-1] / bench_b.iloc[0]) ** (1 / b_years) - 1
    monthly_p = portfolio.resample("ME").last().pct_change().dropna()
    win_rate  = (monthly_p > 0).mean()
    return {
        "cagr": cagr, "sharpe": sh, "sortino": sortino,
        "max_dd": max_dd, "alpha": cagr - b_cagr,
        "win_rate": win_rate, "bench_cagr": b_cagr,
    }


# ── Permutation Test ───────────────────────────────────────────────────────────
def run_permutation_test(close, db, portfolio, n_sim=N_PERMS):
    print(f"\nRunning permutation test ({n_sim} simulations)...", end=" ", flush=True)
    daily_rets = close.pct_change()
    eligible   = [t for t in db if t in close.columns]
    cols       = [c for c in eligible if c in daily_rets.columns]
    ret_matrix = daily_rets[cols].values.astype(float)
    n_tickers  = len(cols)
    trading_days = close.index
    n_days     = len(trading_days)
    years      = (trading_days[-1] - trading_days[0]).days / 365.25
    rng        = np.random.default_rng(seed=42)
    rebal_set  = set(range(0, n_days, REBAL_FREQ))
    rand_cagrs = []

    for _ in range(n_sim):
        port_val = float(INITIAL_CAPITAL)
        held     = rng.choice(n_tickers, size=10, replace=False)
        for i in range(1, n_days):
            if i in rebal_set:
                held = rng.choice(n_tickers, size=10, replace=False)
            day_rets = ret_matrix[i, held]
            valid    = day_rets[~np.isnan(day_rets)]
            if len(valid):
                port_val *= 1.0 + np.mean(valid)
        rand_cagrs.append((port_val / INITIAL_CAPITAL) ** (1 / years) - 1)

    years_p  = (portfolio.index[-1] - portfolio.index[0]).days / 365.25
    arm_cagr = (portfolio.iloc[-1] / portfolio.iloc[0]) ** (1 / years_p) - 1
    arr      = np.array(rand_cagrs)
    pct      = (arr < arm_cagr).mean() * 100
    print("done.")
    return pct, arr, arm_cagr


# ── Plotting ───────────────────────────────────────────────────────────────────
def plot_equity(winner_port, baseline_port, spy, winner_label, metrics_w, metrics_b):
    bench = spy.reindex(winner_port.index).ffill()
    fig, axes = plt.subplots(2, 1, figsize=(14, 9),
                             gridspec_kw={"height_ratios": [3, 1]})
    fig.patch.set_facecolor("#0f0f0f")
    for ax in axes:
        ax.set_facecolor("#1a1a2e")

    ax1 = axes[0]
    bench_n  = bench         / bench.iloc[0]          * 100
    winner_n = winner_port   / winner_port.iloc[0]    * 100
    base_n   = baseline_port / baseline_port.iloc[0]  * 100

    ax1.plot(bench_n.index,  bench_n.values,  color="#888888", linewidth=1.5,
             linestyle="--", label="SPY Buy & Hold", alpha=0.7)
    ax1.plot(base_n.index,   base_n.values,   color="#4da6ff", linewidth=1.5,
             alpha=0.75, label=f"Baseline (original params)  CAGR {metrics_b['cagr']:.1%}")
    ax1.plot(winner_n.index, winner_n.values, color="#00ff88", linewidth=2,
             label=f"Winner: {winner_label}  CAGR {metrics_w['cagr']:.1%}")
    ax1.axvline(pd.Timestamp("2020-01-01"), color="#ffaa00",
                linewidth=1.2, linestyle="--", alpha=0.6, label="OOS start (2020)")

    ax1.set_title("ARM Phase 2 — Optimized Parameters vs Baseline vs SPY",
                  color="white", fontsize=13, fontweight="bold")
    ax1.set_ylabel("Growth of $100", color="#aaaaaa")
    ax1.tick_params(colors="#aaaaaa")
    ax1.spines[:].set_color("#333355")
    ax1.grid(alpha=0.15, color="#444466")
    ax1.legend(facecolor="#1a1a2e", labelcolor="white", fontsize=9)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    ax2 = axes[1]
    for port, color, label in [
        (winner_port, "#00ff88", "Winner"),
        (baseline_port, "#4da6ff", "Baseline"),
    ]:
        roll_max = port.cummax()
        dd = (port - roll_max) / roll_max * 100
        ax2.plot(dd.index, dd.values, color=color, linewidth=1, label=label)
    ax2.axvline(pd.Timestamp("2020-01-01"), color="#ffaa00",
                linewidth=1.2, linestyle="--", alpha=0.6)
    ax2.set_ylabel("Drawdown %", color="#aaaaaa")
    ax2.tick_params(colors="#aaaaaa")
    ax2.spines[:].set_color("#333355")
    ax2.grid(alpha=0.15, color="#444466")
    ax2.legend(facecolor="#1a1a2e", labelcolor="white", fontsize=8)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    plt.tight_layout(pad=2.0)
    plt.savefig("optimizer_results.png", dpi=150, bbox_inches="tight", facecolor="#0f0f0f")
    print("    Chart saved -> optimizer_results.png")


def plot_permutation(rand_cagrs, arm_cagr, spy_cagr, label):
    arr     = np.array(rand_cagrs) * 100
    arm_pct = arm_cagr * 100
    spy_pct = spy_cagr * 100

    fig, ax = plt.subplots(figsize=(12, 5))
    fig.patch.set_facecolor("#0f0f0f")
    ax.set_facecolor("#1a1a2e")
    ax.hist(arr, bins=60, color="#4da6ff", alpha=0.6, edgecolor="none",
            label="1,000 random portfolios")
    ax.axvline(np.percentile(arr, 95), color="#ffaa00", linewidth=1.5,
               linestyle="--", label=f"95th pct ({np.percentile(arr,95):.1f}%)")
    ax.axvline(spy_pct, color="#aaaaff", linewidth=1.5, linestyle=":",
               label=f"SPY ({spy_pct:.1f}%)")
    ax.axvline(arm_pct, color="#00ff88", linewidth=2.5,
               label=f"ARM optimized ({arm_pct:.1f}%)")
    pct = (np.array(rand_cagrs) < arm_cagr).mean() * 100
    ax.set_title(f"ARM (optimized) beats {pct:.1f}% of random portfolios",
                 color="white", fontsize=13, fontweight="bold")
    ax.set_xlabel("CAGR (%)", color="#aaaaaa")
    ax.set_ylabel("Frequency", color="#aaaaaa")
    ax.tick_params(colors="#aaaaaa")
    ax.spines[:].set_color("#333355")
    ax.grid(alpha=0.15, color="#444466", axis="x")
    ax.legend(facecolor="#1a1a2e", labelcolor="white", fontsize=10)
    plt.tight_layout()
    plt.savefig("optimizer_permutation.png", dpi=150, bbox_inches="tight",
                facecolor="#0f0f0f")
    print("    Chart saved -> optimizer_permutation.png\n")


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    print("\n" + "=" * 64)
    print("   ARM Phase 2 — Parameter Optimizer")
    print(f"   Grid: {len(PARAM_GRID)} combinations  |  Optimizing on 2010-2019")
    print("=" * 64 + "\n")

    close, high, low, volume = download_data()
    db  = build_signal_db(close, high, low, volume)
    spy = download_benchmark()

    # Split index masks
    in_mask  = close.index <= INSAMPLE_END
    oos_mask = close.index >= OOS_START

    print(f"[3/4] Grid search across {len(PARAM_GRID)} parameter combos (in-sample 2010-2019)...\n")

    results = []
    for idx, (adx_t, adx_r, rsi, mom_min, mom_slots) in enumerate(PARAM_GRID):
        p = Params(adx_t, adx_r, rsi, mom_min, mom_slots)
        port_in = run_backtest(db, close, p, date_mask=in_mask)
        sh      = sharpe(port_in)
        results.append((sh, p, port_in))

        if (idx + 1) % 50 == 0 or (idx + 1) == len(PARAM_GRID):
            print(f"    {idx+1}/{len(PARAM_GRID)} combos tested...", end="\r")

    results.sort(key=lambda x: x[0], reverse=True)
    print(f"\n    [OK] Grid search complete\n")

    # ── Top 10 in-sample ──
    print("=" * 72)
    print("  TOP 10 — IN-SAMPLE (2010-2019) by Sharpe")
    print("=" * 72)
    print(f"  {'#':<3} {'Sharpe':>7}  {'Parameters':<55}")
    print("  " + "-" * 68)
    for i, (sh, p, _) in enumerate(results[:TOP_N]):
        print(f"  {i+1:<3} {sh:>7.3f}  {p.label()}")

    # ── Validate top 10 OOS ──
    print(f"\n  Validating top {TOP_N} on OUT-OF-SAMPLE (2020-2024)...\n")

    oos_results = []
    spy_oos     = spy[spy.index >= OOS_START]

    for rank, (in_sh, p, _) in enumerate(results[:TOP_N]):
        port_oos = run_backtest(db, close, p, date_mask=oos_mask)
        m        = full_metrics(port_oos, spy_oos)
        oos_results.append((m["sharpe"], m["cagr"], m["max_dd"], m["alpha"], in_sh, p, port_oos))

    oos_results.sort(key=lambda x: x[0], reverse=True)

    print("=" * 72)
    print("  TOP 10 — OUT-OF-SAMPLE (2020-2024) — ranked by Sharpe")
    print("=" * 72)
    print(f"  {'#':<3} {'OOS Sh':>7}  {'OOS CAGR':>9}  {'MaxDD':>7}  {'Alpha':>7}  {'IS Sh':>6}  Parameters")
    print("  " + "-" * 68)
    for i, (oos_sh, oos_cagr, max_dd, alpha, in_sh, p, _) in enumerate(oos_results):
        beat = "BEAT" if alpha > 0 else "MISS"
        print(f"  {i+1:<3} {oos_sh:>7.3f}  {oos_cagr:>9.1%}  {max_dd:>7.1%}  {alpha:>7.1%} ({beat})  {in_sh:>6.3f}  {p.label()}")

    # ── Winner: best OOS Sharpe ──
    best_oos_sh, best_cagr, best_dd, best_alpha, best_in_sh, winner_p, winner_oos = oos_results[0]

    print(f"\n  WINNER (best OOS Sharpe): {winner_p.label()}")
    print(f"  OOS Sharpe {best_oos_sh:.3f}  |  OOS CAGR {best_cagr:.1%}  |  MaxDD {best_dd:.1%}\n")

    # Full portfolio (all years) for winner and baseline
    print("[4/4] Running full 2010-2024 backtests for winner and baseline comparison...")
    winner_full   = run_backtest(db, close, winner_p)
    baseline_p    = Params(adx_trend=25, adx_range=20, rsi_os=35, mom_min=0.05, mom_slots=6)
    baseline_full = run_backtest(db, close, baseline_p)

    spy_full   = spy.reindex(winner_full.index).ffill()
    metrics_w  = full_metrics(winner_full,   spy_full)
    metrics_b  = full_metrics(baseline_full, spy_full)

    print("\n" + "=" * 64)
    print("  WINNER vs BASELINE vs SPY — Full Period (2010-2024)")
    print("=" * 64)
    rows = [
        ("CAGR",             "cagr",   "{:.1%}"),
        ("Sharpe Ratio",     "sharpe", "{:.3f}"),
        ("Sortino Ratio",    "sortino","{:.2f}"),
        ("Max Drawdown",     "max_dd", "{:.1%}"),
        ("Alpha over SPY",   "alpha",  "{:.1%}"),
        ("Monthly Win Rate", "win_rate","{:.1%}"),
    ]
    print(f"  {'Metric':<22} {'Winner':>10}  {'Baseline':>10}  {'SPY':>8}")
    print("  " + "-" * 55)
    spy_cagr = metrics_w["bench_cagr"]
    spy_row  = {"cagr": spy_cagr, "sharpe": 0.84, "sortino": 0.0,
                "max_dd": 0.0,    "alpha": 0.0,   "win_rate": 0.0}
    for label, key, fmt in rows:
        w = fmt.format(metrics_w[key])
        b = fmt.format(metrics_b[key])
        s = fmt.format(spy_row[key]) if key in ("cagr", "sharpe") else "—"
        print(f"  {label:<22} {w:>10}  {b:>10}  {s:>8}")
    print("=" * 64)

    # Permutation test on winner (full period)
    pct, rand_cagrs, arm_cagr = run_permutation_test(close, db, winner_full)
    spy_b    = spy.reindex(winner_full.index).ffill()
    spy_cagr_full = (spy_b.iloc[-1] / spy_b.iloc[0]) ** \
                    (1 / ((winner_full.index[-1] - winner_full.index[0]).days / 365.25)) - 1

    print(f"\n  Permutation result: ARM beats {pct:.1f}% of random portfolios", end=" ")
    if pct >= 95:
        print("-> SIGNIFICANT (p < 0.05)")
    elif pct >= 90:
        print("-> LIKELY REAL (p < 0.10)")
    else:
        print("-> WEAK")

    print("\nGenerating charts...")
    plot_equity(winner_full, baseline_full, spy,
                winner_p.label(), metrics_w, metrics_b)
    plot_permutation(rand_cagrs, arm_cagr, spy_cagr_full, winner_p.label())
    print("\nDone. Open optimizer_results.png and optimizer_permutation.png\n")


if __name__ == "__main__":
    main()
