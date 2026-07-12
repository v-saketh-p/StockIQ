"use client";

import { useEffect, useState } from "react";
import { RefreshCw, TrendingUp, Zap, AlertCircle } from "lucide-react";

interface ArmStock {
  ticker:       string;
  regime:       "TRENDING" | "RANGING" | "NEUTRAL";
  signal:       "MOM_BUY" | "MR_BUY" | "WATCH" | "-";
  momentum:     number;
  adx:          number;
  rsi:          number;
  vol_ratio:    number;
  plus_di:      number;
  minus_di:     number;
  price:        number;
  rank:         number;
  in_portfolio: boolean;
}

interface ArmData {
  momentum_picks:    ArmStock[];
  mr_picks:          ArmStock[];
  all_stocks:        ArmStock[];
  generated_at:      string;
  cache_age_minutes: number;
  cached:            boolean;
  last_rebalance:    string;
  next_rebalance:    string;
  days_remaining:    number;
  locked:            boolean;
}

const REGIME_COLOR: Record<string, string> = {
  TRENDING: "#22c55e",
  RANGING:  "#f59e0b",
  NEUTRAL:  "#6b7280",
};

const SIGNAL_COLOR: Record<string, string> = {
  MOM_BUY: "#22c55e",
  MR_BUY:  "#06b6d4",
  WATCH:   "#f59e0b",
  "-":     "#6b7280",
};

const SIGNAL_LABEL: Record<string, string> = {
  MOM_BUY: "MOM BUY",
  MR_BUY:  "MR BUY",
  WATCH:   "WATCH",
  "-":     "—",
};

function RegimeBadge({ regime }: { regime: string }) {
  const color = REGIME_COLOR[regime] ?? "#6b7280";
  return (
    <span className="text-xs font-bold px-2 py-0.5 rounded-md"
      style={{ background: `${color}1a`, color, border: `1px solid ${color}33` }}>
      {regime}
    </span>
  );
}

function SignalBadge({ signal }: { signal: string }) {
  const color = SIGNAL_COLOR[signal] ?? "#6b7280";
  return (
    <span className="text-xs font-bold px-2 py-0.5 rounded-md tabular-nums"
      style={{ background: `${color}1a`, color, border: `1px solid ${color}33` }}>
      {SIGNAL_LABEL[signal] ?? signal}
    </span>
  );
}

function PickCard({ stock, onSelect }: { stock: ArmStock; onSelect: (t: string) => void }) {
  const isMom = stock.signal === "MOM_BUY";
  const color  = isMom ? "#22c55e" : "#06b6d4";
  return (
    <button
      onClick={() => onSelect(stock.ticker)}
      className="rounded-xl p-4 flex flex-col gap-2 text-left transition-all hover:opacity-80 w-full"
      style={{ background: "var(--surface)", border: `1px solid var(--border)`, borderTop: `2px solid ${color}` }}
    >
      <div className="flex items-center justify-between">
        <span className="text-xl font-extrabold" style={{ color: "var(--text)" }}>{stock.ticker}</span>
        <SignalBadge signal={stock.signal} />
      </div>
      <div className="flex items-center gap-1.5 flex-wrap">
        <RegimeBadge regime={stock.regime} />
        <span className="text-xs" style={{ color: "var(--muted)" }}>#{stock.rank}</span>
      </div>
      <div className="grid grid-cols-3 gap-2 mt-1">
        <div>
          <div className="text-xs" style={{ color: "var(--muted)" }}>12-1 Mom</div>
          <div className="text-sm font-bold tabular-nums"
            style={{ color: stock.momentum >= 0 ? "#22c55e" : "#ef4444" }}>
            {stock.momentum >= 0 ? "+" : ""}{stock.momentum.toFixed(1)}%
          </div>
        </div>
        <div>
          <div className="text-xs" style={{ color: "var(--muted)" }}>ADX</div>
          <div className="text-sm font-bold tabular-nums" style={{ color: "var(--text)" }}>{stock.adx.toFixed(1)}</div>
        </div>
        <div>
          <div className="text-xs" style={{ color: "var(--muted)" }}>RSI</div>
          <div className="text-sm font-bold tabular-nums" style={{ color: "var(--text)" }}>{stock.rsi.toFixed(1)}</div>
        </div>
      </div>
    </button>
  );
}

export default function ARMSignals({ onSelectTicker }: { onSelectTicker: (t: string) => void }) {
  const [data,     setData]     = useState<ArmData | null>(null);
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState<string | null>(null);
  const [sortKey,  setSortKey]  = useState<keyof ArmStock>("rank");
  const [sortAsc,  setSortAsc]  = useState(true);
  const [lockMode, setLockMode] = useState(() => {
    try { return localStorage.getItem("arm_lock_mode") !== "false"; } catch { return true; }
  });

  function toggleLock() {
    setLockMode(prev => {
      const next = !prev;
      try { localStorage.setItem("arm_lock_mode", String(next)); } catch {}
      return next;
    });
  }

  async function fetchSignals(refresh = false) {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`http://localhost:8000/api/arm/signals${refresh ? "?refresh=true" : ""}`);
      if (!res.ok) { const j = await res.json(); throw new Error(j.detail || "Failed"); }
      setData(await res.json());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { fetchSignals(); }, []);

  function toggleSort(key: keyof ArmStock) {
    if (sortKey === key) setSortAsc(a => !a);
    else { setSortKey(key); setSortAsc(key === "rank"); }
  }

  const sortedStocks = data
    ? [...data.all_stocks].sort((a, b) => {
        const av = a[sortKey] as number;
        const bv = b[sortKey] as number;
        return sortAsc ? (av > bv ? 1 : -1) : (av < bv ? 1 : -1);
      })
    : [];

  const allPicks = data ? [...data.momentum_picks, ...data.mr_picks] : [];

  function ColHeader({ label, k }: { label: string; k: keyof ArmStock }) {
    const active = sortKey === k;
    return (
      <th
        className="px-3 py-2 text-left text-xs font-bold uppercase tracking-wider cursor-pointer select-none hover:opacity-70 transition-opacity"
        style={{ color: active ? "var(--text)" : "var(--muted)" }}
        onClick={() => toggleSort(k)}
      >
        {label} {active ? (sortAsc ? "↑" : "↓") : ""}
      </th>
    );
  }

  return (
    <div className="flex flex-col gap-5">

      {/* Header */}
      <div className="rounded-2xl overflow-hidden"
        style={{ background: "var(--surface)", border: "1px solid var(--border2)", boxShadow: "0 1px 4px var(--shadow)" }}>
        <div className="h-0.5" style={{ background: "linear-gradient(90deg,#10b981,#06b6d4)" }} />
        <div className="px-6 py-5 flex items-center justify-between gap-4">
          <div className="flex flex-col gap-1">
            <div className="flex items-center gap-2">
              <Zap size={20} style={{ color: "#10b981" }} />
              <h1 className="text-2xl font-extrabold tracking-tight" style={{ color: "var(--text)" }}>
                ARM Signal Scanner
              </h1>
            </div>
            <p className="text-xs" style={{ color: "var(--muted)" }}>
              Adaptive Regime Momentum — 113 stocks · bi-weekly rebalance · ADX 22/15 · RSI&lt;30 · Mom&gt;10%
            </p>
            {data && (
              <p className="text-xs" style={{ color: "var(--muted2)" }}>
                {lockMode
                  ? data.locked
                    ? `Locked · next rebalance ${new Date(data.next_rebalance + "T00:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" })} · ${data.days_remaining} trading days left`
                    : `Rebalanced today · next in 10 trading days`
                  : `Live signals · refresh anytime`}
              </p>
            )}
          </div>

          <div className="flex items-center gap-3">
            {/* Lock mode toggle */}
            <button
              onClick={toggleLock}
              title={lockMode ? "Switch to live mode (refresh anytime)" : "Switch to locked mode (bi-weekly rebalance)"}
              className="flex items-center gap-2 text-xs px-3 py-2 rounded-lg font-semibold transition-all hover:opacity-80"
              style={lockMode
                ? { background: "rgba(245,158,11,0.12)", color: "#f59e0b", border: "1px solid rgba(245,158,11,0.3)" }
                : { background: "rgba(107,114,128,0.12)", color: "var(--muted)", border: "1px solid var(--border)" }}
            >
              {lockMode ? "🔒 Locked" : "🔓 Live"}
            </button>

            {/* Refresh button */}
            <button
              onClick={() => fetchSignals(true)}
              disabled={loading || (lockMode && (data?.locked ?? false))}
              title={lockMode && data?.locked ? `Locked until ${data?.next_rebalance} — switch to Live mode to refresh` : "Refresh signals"}
              className="flex items-center gap-2 text-xs px-4 py-2 rounded-lg font-semibold transition-all hover:opacity-80 disabled:opacity-40 disabled:cursor-not-allowed"
              style={{ background: "rgba(16,185,129,0.12)", color: "#10b981", border: "1px solid rgba(16,185,129,0.25)" }}
            >
              <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
              {loading ? "Scanning..." : "Refresh"}
            </button>
          </div>
        </div>
      </div>

      {/* Loading */}
      {loading && !data && (
        <div className="flex flex-col items-center justify-center gap-4 py-20"
          style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 16 }}>
          <RefreshCw size={28} className="animate-spin" style={{ color: "#10b981" }} />
          <div className="text-center">
            <div className="text-sm font-semibold" style={{ color: "var(--text)" }}>Scanning 113 stocks...</div>
            <div className="text-xs mt-1" style={{ color: "var(--muted)" }}>This takes about 30–60 seconds on first load</div>
          </div>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="flex items-center gap-3 px-4 py-3 rounded-xl"
          style={{ background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.2)" }}>
          <AlertCircle size={16} style={{ color: "#ef4444" }} />
          <span className="text-sm" style={{ color: "#ef4444" }}>{error}</span>
        </div>
      )}

      {data && (
        <>
          {/* Current picks */}
          <div className="flex flex-col gap-3">
            <div className="flex items-center gap-2">
              <TrendingUp size={14} style={{ color: "#10b981" }} />
              <span className="text-xs font-bold uppercase tracking-widest" style={{ color: "var(--muted2)" }}>
                Current Portfolio ({allPicks.length} holdings)
              </span>
              <span className="text-xs px-2 py-0.5 rounded-md font-semibold"
                style={{ background: "rgba(16,185,129,0.1)", color: "#10b981", border: "1px solid rgba(16,185,129,0.2)" }}>
                {data.momentum_picks.length} MOM · {data.mr_picks.length} MR
              </span>
            </div>
            {allPicks.length === 0 ? (
              <div className="text-sm px-4 py-3 rounded-xl" style={{ color: "var(--muted)", background: "var(--surface)", border: "1px solid var(--border)" }}>
                No picks meeting signal criteria right now.
              </div>
            ) : (
              <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))" }}>
                {allPicks.map(s => (
                  <PickCard key={s.ticker} stock={s} onSelect={t => { onSelectTicker(t); }} />
                ))}
              </div>
            )}
          </div>

          {/* Divider */}
          <div style={{ height: 1, background: "var(--border)" }} />

          {/* Full universe table */}
          <div className="flex flex-col gap-3">
            <span className="text-xs font-bold uppercase tracking-widest" style={{ color: "var(--muted2)" }}>
              Full Universe — {data.all_stocks.length} stocks · click column to sort
            </span>
            <div className="rounded-xl overflow-hidden" style={{ border: "1px solid var(--border)" }}>
              <div className="overflow-x-auto">
                <table className="w-full text-sm border-collapse">
                  <thead>
                    <tr style={{ background: "var(--surface2)", borderBottom: "1px solid var(--border)" }}>
                      <ColHeader label="#"        k="rank"      />
                      <th className="px-3 py-2 text-left text-xs font-bold uppercase tracking-wider" style={{ color: "var(--muted)" }}>Ticker</th>
                      <th className="px-3 py-2 text-left text-xs font-bold uppercase tracking-wider" style={{ color: "var(--muted)" }}>Regime</th>
                      <th className="px-3 py-2 text-left text-xs font-bold uppercase tracking-wider" style={{ color: "var(--muted)" }}>Signal</th>
                      <ColHeader label="12-1 Mom%" k="momentum"  />
                      <ColHeader label="ADX"       k="adx"       />
                      <ColHeader label="RSI"       k="rsi"       />
                      <ColHeader label="Vol Ratio" k="vol_ratio" />
                    </tr>
                  </thead>
                  <tbody>
                    {sortedStocks.map((s, i) => (
                      <tr
                        key={s.ticker}
                        onClick={() => onSelectTicker(s.ticker)}
                        className="cursor-pointer transition-colors hover:opacity-80"
                        style={{
                          background: s.in_portfolio
                            ? "rgba(16,185,129,0.04)"
                            : i % 2 === 0 ? "var(--surface)" : "var(--surface2)",
                          borderBottom: "1px solid var(--border)",
                          borderLeft: s.in_portfolio ? "2px solid #10b981" : "2px solid transparent",
                        }}
                      >
                        <td className="px-3 py-2 tabular-nums text-xs" style={{ color: "var(--muted)" }}>{s.rank}</td>
                        <td className="px-3 py-2 font-bold" style={{ color: "var(--text)" }}>
                          <div className="flex items-center gap-1.5">
                            {s.ticker}
                            {s.in_portfolio && (
                              <span className="text-xs px-1 rounded" style={{ background: "rgba(16,185,129,0.15)", color: "#10b981" }}>★</span>
                            )}
                          </div>
                        </td>
                        <td className="px-3 py-2"><RegimeBadge regime={s.regime} /></td>
                        <td className="px-3 py-2"><SignalBadge signal={s.signal} /></td>
                        <td className="px-3 py-2 tabular-nums font-semibold"
                          style={{ color: s.momentum >= 0 ? "#22c55e" : "#ef4444" }}>
                          {s.momentum >= 0 ? "+" : ""}{s.momentum.toFixed(1)}%
                        </td>
                        <td className="px-3 py-2 tabular-nums" style={{ color: "var(--text)" }}>{s.adx.toFixed(1)}</td>
                        <td className="px-3 py-2 tabular-nums" style={{ color: "var(--text)" }}>{s.rsi.toFixed(1)}</td>
                        <td className="px-3 py-2 tabular-nums" style={{ color: "var(--text)" }}>{s.vol_ratio.toFixed(2)}x</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
