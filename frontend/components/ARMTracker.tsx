"use client";

import { useEffect, useState } from "react";
import { RefreshCw, TrendingUp, Target } from "lucide-react";
import { API_BASE } from "@/lib/api";
import {
  AreaChart, Area, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, ReferenceLine,
} from "recharts";

interface PickStat {
  ticker:        string;
  signal:        "MOM_BUY" | "MR_BUY";
  regime:        string;
  entry_price:   number;
  current_price: number;
  return_pct:    number;
  momentum:      number | null;
}

interface ChartPoint {
  date: string;
  arm:  number;
  spy?: number;
}

interface TrackerData {
  rebalance_date:   string;
  next_rebalance:   string;
  days_held:        number;
  days_remaining:   number;
  portfolio_return: number;
  spy_return:       number | null;
  alpha:            number | null;
  picks:            PickStat[];
  chart:            ChartPoint[];
}

function fmt(v: number) {
  return `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`;
}

function fmtDate(iso: string) {
  return new Date(iso + "T00:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function CustomTooltip({ active, payload, label }: { active?: boolean; payload?: { dataKey: string; value: number; color: string }[]; label?: string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="px-3 py-2 rounded-lg text-xs"
      style={{ background: "var(--surface)", border: "1px solid var(--border)", color: "var(--text)" }}>
      <div className="font-semibold mb-1">{label}</div>
      {payload.map(p => (
        <div key={p.dataKey} className="flex items-center gap-2">
          <span style={{ color: p.color }}>●</span>
          <span style={{ color: "var(--muted)" }}>{p.dataKey === "arm" ? "ARM" : "SPY"}</span>
          <span className="font-bold tabular-nums" style={{ color: p.value >= 0 ? "#22c55e" : "#ef4444" }}>
            {fmt(p.value)}
          </span>
        </div>
      ))}
    </div>
  );
}

export default function ARMTracker({ onSelectTicker }: { onSelectTicker: (t: string) => void }) {
  const [data,    setData]    = useState<TrackerData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/arm/performance`);
      if (!res.ok) { const j = await res.json(); throw new Error(j.detail || "Failed"); }
      setData(await res.json());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  return (
    <div className="flex flex-col gap-5">

      {/* Header */}
      <div className="rounded-2xl overflow-hidden"
        style={{ background: "var(--surface)", border: "1px solid var(--border2)", boxShadow: "0 1px 4px var(--shadow)" }}>
        <div className="h-0.5" style={{ background: "linear-gradient(90deg,#10b981,#06b6d4)" }} />
        <div className="px-6 py-5 flex items-center justify-between gap-4">
          <div className="flex flex-col gap-1">
            <div className="flex items-center gap-2">
              <Target size={20} style={{ color: "#10b981" }} />
              <h1 className="text-2xl font-extrabold tracking-tight" style={{ color: "var(--text)" }}>
                ARM Portfolio Tracker
              </h1>
            </div>
            {data ? (
              <p className="text-xs" style={{ color: "var(--muted)" }}>
                Rebalanced {fmtDate(data.rebalance_date)} · {data.days_held} trading day{data.days_held !== 1 ? "s" : ""} held · {data.days_remaining} remaining · Next {fmtDate(data.next_rebalance)}
              </p>
            ) : (
              <p className="text-xs" style={{ color: "var(--muted)" }}>
                Equal-weight portfolio · tracked vs S&P 500 since rebalance date
              </p>
            )}
          </div>
          <button
            onClick={load}
            disabled={loading}
            className="flex items-center gap-2 text-xs px-4 py-2 rounded-lg font-semibold transition-all hover:opacity-80 disabled:opacity-40"
            style={{ background: "rgba(16,185,129,0.12)", color: "#10b981", border: "1px solid rgba(16,185,129,0.25)" }}
          >
            <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
            {loading ? "Loading..." : "Refresh"}
          </button>
        </div>
      </div>

      {/* Loading */}
      {loading && !data && (
        <div className="flex items-center justify-center gap-3 py-20 rounded-2xl"
          style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
          <RefreshCw size={20} className="animate-spin" style={{ color: "#10b981" }} />
          <span className="text-sm" style={{ color: "var(--muted)" }}>Fetching performance data...</span>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="px-4 py-3 rounded-xl text-sm"
          style={{ background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.2)", color: "#ef4444" }}>
          {error}
        </div>
      )}

      {data && (
        <>
          {/* Summary stats */}
          <div className="grid grid-cols-3 gap-4">
            {([
              {
                label: "ARM Portfolio",
                value: fmt(data.portfolio_return),
                color: data.portfolio_return >= 0 ? "#22c55e" : "#ef4444",
                sub:   `${data.picks.length} equal-weight picks`,
              },
              {
                label: "S&P 500",
                value: data.spy_return !== null ? fmt(data.spy_return) : "—",
                color: (data.spy_return ?? 0) >= 0 ? "#22c55e" : "#ef4444",
                sub:   "SPY benchmark",
              },
              {
                label: "Alpha",
                value: data.alpha !== null ? fmt(data.alpha) : "—",
                color: (data.alpha ?? 0) >= 0 ? "#10b981" : "#ef4444",
                sub:   "vs S&P 500",
              },
            ] as const).map(stat => (
              <div key={stat.label} className="rounded-xl px-5 py-4 flex flex-col gap-1"
                style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
                <div className="text-xs font-semibold uppercase tracking-wider" style={{ color: "var(--muted)" }}>{stat.label}</div>
                <div className="text-2xl font-extrabold tabular-nums" style={{ color: stat.color }}>{stat.value}</div>
                <div className="text-xs" style={{ color: "var(--muted2)" }}>{stat.sub}</div>
              </div>
            ))}
          </div>

          {/* Chart */}
          {data.chart.length > 1 && (
            <div className="rounded-2xl px-5 pt-5 pb-3"
              style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
              <div className="text-xs font-bold uppercase tracking-widest mb-4" style={{ color: "var(--muted2)" }}>
                Return since rebalance — ARM vs S&P 500
              </div>
              <ResponsiveContainer width="100%" height={220}>
                <AreaChart data={data.chart} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
                  <defs>
                    <linearGradient id="armGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%"  stopColor="#10b981" stopOpacity={0.25} />
                      <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                    </linearGradient>
                    <linearGradient id="spyGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%"  stopColor="#6b7280" stopOpacity={0.15} />
                      <stop offset="95%" stopColor="#6b7280" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                  <ReferenceLine y={0} stroke="var(--border2)" strokeWidth={1} />
                  <XAxis
                    dataKey="date"
                    tick={{ fontSize: 11, fill: "var(--muted)" }}
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={d => fmtDate(d)}
                  />
                  <YAxis
                    tick={{ fontSize: 11, fill: "var(--muted)" }}
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={v => `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`}
                    width={54}
                  />
                  <Tooltip content={<CustomTooltip />} />
                  <Area type="monotone" dataKey="spy" stroke="#6b7280" strokeWidth={1.5}
                    fill="url(#spyGrad)" dot={false} />
                  <Area type="monotone" dataKey="arm" stroke="#10b981" strokeWidth={2}
                    fill="url(#armGrad)" dot={false} />
                </AreaChart>
              </ResponsiveContainer>
              <div className="flex items-center gap-4 mt-2 justify-end">
                <div className="flex items-center gap-1.5 text-xs" style={{ color: "var(--muted)" }}>
                  <span className="inline-block w-6 h-0.5 rounded" style={{ background: "#10b981" }} /> ARM Portfolio
                </div>
                <div className="flex items-center gap-1.5 text-xs" style={{ color: "var(--muted)" }}>
                  <span className="inline-block w-6 h-0.5 rounded" style={{ background: "#6b7280" }} /> S&P 500
                </div>
              </div>
            </div>
          )}

          {/* Holdings grid */}
          <div className="flex flex-col gap-3">
            <div className="flex items-center gap-2">
              <TrendingUp size={14} style={{ color: "#10b981" }} />
              <span className="text-xs font-bold uppercase tracking-widest" style={{ color: "var(--muted2)" }}>
                Current Holdings ({data.picks.length}) — sorted by return
              </span>
            </div>
            <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))" }}>
              {[...data.picks].sort((a, b) => b.return_pct - a.return_pct).map(p => {
                const isPos     = p.return_pct >= 0;
                const isMom     = p.signal === "MOM_BUY";
                const accent    = isMom ? "#22c55e" : "#06b6d4";
                return (
                  <button
                    key={p.ticker}
                    onClick={() => onSelectTicker(p.ticker)}
                    className="rounded-xl p-4 flex flex-col gap-2 text-left transition-all hover:opacity-80 w-full"
                    style={{ background: "var(--surface)", border: "1px solid var(--border)", borderTop: `2px solid ${accent}` }}
                  >
                    <div className="flex items-center justify-between gap-1">
                      <span className="text-lg font-extrabold" style={{ color: "var(--text)" }}>{p.ticker}</span>
                      <span className="text-sm font-bold tabular-nums" style={{ color: isPos ? "#22c55e" : "#ef4444" }}>
                        {fmt(p.return_pct)}
                      </span>
                    </div>
                    <div className="text-xs tabular-nums" style={{ color: "var(--muted)" }}>
                      ${p.entry_price.toFixed(2)} → ${p.current_price.toFixed(2)}
                    </div>
                    <span className="text-xs font-bold px-2 py-0.5 rounded-md self-start"
                      style={{ background: `${accent}1a`, color: accent, border: `1px solid ${accent}33` }}>
                      {isMom ? "MOM" : "MR"}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
