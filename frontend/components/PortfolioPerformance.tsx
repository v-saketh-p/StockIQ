"use client";

import { useEffect, useState, useMemo } from "react";
import { RefreshCw } from "lucide-react";
import {
  ComposedChart, Area, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid,
} from "recharts";
import type { Position, Transaction } from "./PortfolioTracker";

interface ChartPoint {
  date:       string;
  value:      number;      // indexed: 100 = start (from backend)
  absValue?:  number;      // absolute portfolio value
  benchmark?: number;
  plotValue?: number;      // what the chart Area actually renders (absValue)
}

interface PerfStats {
  startDate:       string;
  startValue:      number;
  currentValue:    number;
  totalReturn:     number;
  benchmarkReturn: number | null;
  alpha:           number | null;
}

interface PerfData {
  chart: ChartPoint[];
  stats: PerfStats;
}

const PERIODS = ["1M", "3M", "6M", "YTD", "1Y", "All"] as const;
type Period = typeof PERIODS[number];

function cutoffDate(period: Period): Date | null {
  const now = new Date();
  if (period === "All") return null;
  if (period === "1M")  return new Date(now.getFullYear(), now.getMonth() - 1,  now.getDate());
  if (period === "3M")  return new Date(now.getFullYear(), now.getMonth() - 3,  now.getDate());
  if (period === "6M")  return new Date(now.getFullYear(), now.getMonth() - 6,  now.getDate());
  if (period === "YTD") return new Date(now.getFullYear(), 0, 1);
  if (period === "1Y")  return new Date(now.getFullYear() - 1, now.getMonth(), now.getDate());
  return null;
}

function fmtMoney(v: number) {
  const a = Math.abs(v);
  if (a >= 1e6) return `$${(v / 1e6).toFixed(2)}M`;
  if (a >= 1e3) return `$${(v / 1e3).toFixed(1)}K`;
  return `$${v.toFixed(2)}`;
}

function StatPill({ label, value, positive, sub }: {
  label: string; value: string; positive?: boolean | null; sub?: string;
}) {
  const color = positive == null ? "var(--text)"
    : positive ? "#22c55e" : "#ef4444";
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[11px] uppercase tracking-wider" style={{ color: "var(--muted)" }}>{label}</span>
      <span className="text-base font-extrabold tabular-nums" style={{ color }}>
        {value}
      </span>
      {sub && <span className="text-[11px]" style={{ color: "var(--muted)" }}>{sub}</span>}
    </div>
  );
}

interface CustomTooltipProps {
  active?:    boolean;
  payload?:   { value: number; dataKey: string; color: string; payload: ChartPoint }[];
  label?:     string;
  startValue?: number;
}

function CustomTooltip({ active, payload, label, startValue }: CustomTooltipProps) {
  if (!active || !payload?.length) return null;
  const pt = payload[0]?.payload;
  const current = pt?.absValue ?? pt?.plotValue ?? 0;
  const gainPct = startValue && startValue > 0
    ? ((current - startValue) / startValue) * 100
    : null;
  return (
    <div className="rounded-xl px-4 py-3 flex flex-col gap-1.5 text-xs"
      style={{ background: "var(--surface2)", border: "1px solid var(--border)", boxShadow: "0 4px 20px rgba(0,0,0,0.3)" }}>
      <div className="font-semibold mb-1" style={{ color: "var(--muted2)" }}>{label}</div>
      <div className="flex items-center gap-2">
        <span className="w-2 h-2 rounded-full" style={{ background: "#3b82f6" }} />
        <span style={{ color: "var(--muted)" }}>Portfolio</span>
        <span className="ml-auto font-semibold tabular-nums" style={{ color: "var(--text)" }}>
          {fmtMoney(current)}
        </span>
      </div>
      {gainPct != null && (
        <div className="text-[11px]" style={{ color: gainPct >= 0 ? "#22c55e" : "#ef4444" }}>
          {gainPct >= 0 ? "+" : ""}{gainPct.toFixed(2)}% from period start
        </div>
      )}
    </div>
  );
}

export default function PortfolioPerformance({ positions, transactions, netDeposits, usdToGbp = 0.79 }: {
  positions:    Position[];
  transactions: Transaction[];
  netDeposits?: number | null;
  usdToGbp?:   number;
}) {
  const [data,    setData]    = useState<PerfData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState<string | null>(null);
  const [period,  setPeriod]  = useState<Period>("All");

  async function load() {
    if (!transactions.length) return;
    setLoading(true); setError(null);
    try {
      const res = await fetch("http://localhost:8000/api/portfolio/performance", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          transactions: transactions.map(t => ({
            ticker:   t.ticker,
            date:     t.date,
            shares:   t.shares,
            price:    t.price,
            currency: t.currency ?? "USD",
            type:     t.type,
          })),
        }),
      });
      if (!res.ok) { const j = await res.json(); throw new Error(j.detail || "Failed"); }
      setData(await res.json());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Error loading chart");
    } finally { setLoading(false); }
  }

  const posKey = transactions.map(t => t.id).join(",");
  useEffect(() => { setData(null); setError(null); }, [posKey]);
  useEffect(() => { load(); }, [posKey]);

  // Filter chart data for selected period; expose absValue as the plotted value
  const filtered = useMemo(() => {
    if (!data) return [];
    const cutoff = cutoffDate(period);
    const pts = cutoff
      ? data.chart.filter(d => new Date(d.date) >= cutoff)
      : data.chart;
    // Use absolute portfolio value for the chart line
    return pts.map(p => ({ ...p, plotValue: p.absValue ?? p.value }));
  }, [data, period]);

  // TWRR for any period: split at each new position purchase, chain sub-period returns
  const periodStats = useMemo(() => {
    if (!data) return null;

    if (period === "All") {
      const currentValueUsd = data.chart[data.chart.length - 1]?.absValue ?? 0;
      let simpleReturn: number;
      if (netDeposits && netDeposits > 0) {
        // Compare portfolio value in GBP against actual GBP deposits
        const currentValueGbp = currentValueUsd * usdToGbp;
        simpleReturn = ((currentValueGbp - netDeposits) / netDeposits) * 100;
      } else {
        const totalCost = positions.reduce((sum, p) => sum + p.shares * p.avgCost, 0);
        simpleReturn = totalCost > 0 ? ((currentValueUsd - totalCost) / totalCost) * 100 : 0;
      }
      return {
        ...data.stats,
        totalReturn:     parseFloat(simpleReturn.toFixed(2)),
        benchmarkReturn: null,
        alpha:           null,
      };
    }

    const cutoff = cutoffDate(period)!;
    const raw = data.chart.filter(d => new Date(d.date) >= cutoff);
    if (raw.length < 2) return data.stats;

    const first = raw[0];
    const last  = raw[raw.length - 1];

    const navMap: Record<string, number> = {};
    for (const p of raw) { if (p.absValue != null) navMap[p.date] = p.absValue; }
    const sortedDates = Object.keys(navMap).sort();

    // Every buy transaction within this period is a cash injection boundary
    const cfDates = [...new Set(
      transactions
        .filter(t => t.type === "buy" && t.date > first.date && t.date <= last.date)
        .map(t => t.date)
    )].sort();

    if (!cfDates.length) {
      // No new capital — simple (end − start) / start
      const firstAbs = first.absValue ?? first.value;
      const lastAbs  = last.absValue  ?? last.value;
      const ret      = firstAbs > 0 ? ((lastAbs - firstAbs) / firstAbs) * 100 : 0;
      return { ...data.stats, startDate: first.date, totalReturn: parseFloat(ret.toFixed(2)), benchmarkReturn: null, alpha: null };
    }

    // TWRR: split at each cash injection, chain sub-period returns
    const navOnOrAfter = (d: string) => { const x = sortedDates.find(s => s >= d); return x ? navMap[x] : null; };
    const navBefore    = (d: string) => { const x = [...sortedDates].reverse().find(s => s < d); return x ? navMap[x] : null; };

    const boundaries = [first.date, ...cfDates];
    let twrr = 1;
    for (let i = 0; i < boundaries.length; i++) {
      const s = navOnOrAfter(boundaries[i]);
      const e = boundaries[i + 1] ? navBefore(boundaries[i + 1]) : navMap[sortedDates[sortedDates.length - 1]];
      if (s && e && s > 0) twrr *= e / s;
    }
    const ret = (twrr - 1) * 100;

    return {
      ...data.stats,
      startDate:       first.date,
      totalReturn:     parseFloat(ret.toFixed(2)),
      benchmarkReturn: null,
      alpha:           null,
    };
  }, [data, period, positions, transactions, netDeposits, usdToGbp]);

  // X-axis tick sampling
  const xTicks = useMemo(() => {
    if (!filtered.length) return [];
    const n = filtered.length;
    if (n <= 60)  return filtered.map(d => d.date);
    const step = Math.ceil(n / 8);
    return filtered.filter((_, i) => i % step === 0 || i === n - 1).map(d => d.date);
  }, [filtered]);

  if (!transactions.length) return null;

  return (
    <div className="rounded-xl overflow-hidden"
      style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>

      {/* Header */}
      <div className="px-5 pt-4 pb-3 flex items-center justify-between border-b"
        style={{ borderColor: "var(--border)" }}>
        <div>
          <div className="text-sm font-bold" style={{ color: "var(--text)" }}>
            Portfolio Performance
          </div>
          {periodStats && (
            <div className="text-xs mt-0.5" style={{ color: "var(--muted)" }}>
              Since {periodStats.startDate}
            </div>
          )}
        </div>
        <div className="flex items-center gap-2">
          {/* Period buttons */}
          <div className="flex gap-0.5 p-0.5 rounded-lg"
            style={{ background: "var(--surface2)", border: "1px solid var(--border)" }}>
            {PERIODS.map(p => (
              <button key={p} onClick={() => setPeriod(p)}
                className="px-2.5 py-1 rounded-md text-[11px] font-semibold transition-all"
                style={period === p
                  ? { background: "var(--surface)", color: "var(--text)", boxShadow: "0 1px 3px var(--shadow)" }
                  : { color: "var(--muted2)" }}>
                {p}
              </button>
            ))}
          </div>
          <button onClick={load} disabled={loading}
            className="w-7 h-7 flex items-center justify-center rounded-lg hover:opacity-80 disabled:opacity-40 transition-opacity"
            style={{ background: "var(--surface2)", border: "1px solid var(--border2)", color: "var(--muted2)" }}>
            <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
      </div>

      {/* Stats row */}
      {periodStats && !loading && (
        <div className="px-5 pt-3 pb-2 flex items-center gap-8 border-b"
          style={{ borderColor: "var(--border)" }}>
          <StatPill
            label="Portfolio Return"
            value={`${periodStats.totalReturn >= 0 ? "+" : ""}${periodStats.totalReturn.toFixed(2)}%`}
            positive={periodStats.totalReturn >= 0}
            sub={fmtMoney(filtered[filtered.length - 1]?.absValue ?? 0)}
          />
          <div className="flex items-center gap-1.5 ml-auto text-[11px]" style={{ color: "var(--muted)" }}>
            <span className="w-3 h-0.5 rounded" style={{ background: "#3b82f6" }} /> Portfolio
          </div>
        </div>
      )}

      {/* Chart body */}
      <div className="px-2 py-4">
        {loading && (
          <div className="flex items-center justify-center h-48 gap-3">
            <RefreshCw size={16} className="animate-spin" style={{ color: "var(--blue)" }} />
            <span className="text-sm" style={{ color: "var(--muted2)" }}>
              Computing performance history…
            </span>
          </div>
        )}

        {error && !loading && (
          <div className="mx-3 mb-3 rounded-xl px-4 py-3 text-xs"
            style={{ background: "rgba(239,68,68,0.07)", color: "var(--red)", border: "1px solid rgba(239,68,68,0.2)" }}>
            {error}
          </div>
        )}

        {!loading && !error && filtered.length > 0 && (() => {
          const startValue = filtered[0]?.absValue ?? filtered[0]?.plotValue ?? 0;
          return (
            <ResponsiveContainer width="100%" height={220}>
              <ComposedChart data={filtered} margin={{ top: 4, right: 12, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="portfolioGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"  stopColor="#3b82f6" stopOpacity={0.25} />
                    <stop offset="95%" stopColor="#3b82f6" stopOpacity={0.02} />
                  </linearGradient>
                </defs>

                <CartesianGrid vertical={false} stroke="var(--border)" strokeOpacity={0.5} />

                <XAxis dataKey="date" ticks={xTicks}
                  tick={{ fill: "var(--muted)", fontSize: 10 }}
                  axisLine={false} tickLine={false}
                  tickFormatter={d => {
                    const dt = new Date(d);
                    return dt.toLocaleDateString("en-US", { month: "short", day: "numeric" });
                  }}
                />

                <YAxis
                  tick={{ fill: "var(--muted)", fontSize: 10 }}
                  axisLine={false} tickLine={false} width={56}
                  tickFormatter={v => {
                    if (Math.abs(v) >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
                    if (Math.abs(v) >= 1e3) return `$${(v / 1e3).toFixed(0)}K`;
                    return `$${v.toFixed(0)}`;
                  }}
                />

                <Tooltip content={<CustomTooltip startValue={startValue} />} />

                {/* Portfolio — filled area */}
                <Area
                  type="monotone" dataKey="plotValue"
                  stroke="#3b82f6" strokeWidth={2}
                  fill="url(#portfolioGrad)" dot={false}
                  activeDot={{ r: 4, fill: "#3b82f6", stroke: "var(--surface)", strokeWidth: 2 }}
                />
              </ComposedChart>
            </ResponsiveContainer>
          );
        })()}
      </div>
    </div>
  );
}
