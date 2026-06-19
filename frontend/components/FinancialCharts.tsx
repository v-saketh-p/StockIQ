"use client";

import { useEffect, useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  Cell, ReferenceLine,
} from "recharts";

interface Financials {
  ticker: string;
  revenue:   { year: string; value: number }[];
  fcf:       { year: string; value: number }[];
  peHistory: { year: string; pe: number }[];
}

function ChartCard({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className="rounded-xl p-4 flex flex-col gap-3"
      style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
    >
      <div>
        <div className="text-xs font-bold uppercase tracking-widest" style={{ color: "var(--muted2)" }}>
          {title}
        </div>
        <div className="text-xs mt-0.5" style={{ color: "var(--muted)" }}>{subtitle}</div>
      </div>
      {children}
    </div>
  );
}

const BLUE   = "#3b82f6";
const GREEN  = "#22c55e";
const RED    = "#ef4444";
const AMBER  = "#f59e0b";
const MUTED  = "#6b7280";

function dollarTick(v: number) {
  if (Math.abs(v) >= 1000) return `$${(v / 1000).toFixed(0)}T`;
  return `$${v}B`;
}

function CustomTooltip({
  active, payload, label, unit,
}: {
  active?: boolean;
  payload?: { value: number }[];
  label?: string;
  unit: string;
}) {
  if (!active || !payload?.length) return null;
  const val = payload[0].value;
  return (
    <div
      className="rounded-lg px-3 py-2 text-xs"
      style={{ background: "var(--surface2)", border: "1px solid var(--border2)", color: "var(--text)" }}
    >
      <div style={{ color: "var(--muted)" }}>{label}</div>
      <div className="font-bold mt-0.5">{unit === "$B" ? `$${val.toFixed(2)}B` : `${val}x`}</div>
    </div>
  );
}

export default function FinancialCharts({ ticker }: { ticker: string }) {
  const [data, setData]       = useState<Financials | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    setData(null);
    fetch(`http://localhost:8000/api/stock/${ticker}/financials`)
      .then(r => r.ok ? r.json() : null)
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [ticker]);

  if (loading) {
    return (
      <div className="grid grid-cols-3 gap-4">
        {["Revenue (Annual)", "Free Cash Flow (Annual)", "P/E Ratio History"].map(t => (
          <ChartCard key={t} title={t} subtitle="Loading…">
            <div className="h-36 flex items-center justify-center">
              <div className="text-xs" style={{ color: "var(--muted)" }}>Loading…</div>
            </div>
          </ChartCard>
        ))}
      </div>
    );
  }

  if (!data) return null;

  const { revenue, fcf, peHistory } = data;

  return (
    <div className="grid grid-cols-3 gap-4">

      {/* ── Revenue ── */}
      <ChartCard title="Revenue (Annual)" subtitle="Total revenue in $B — fiscal year">
        {revenue.length ? (
          <ResponsiveContainer width="100%" height={160}>
            <BarChart data={revenue} margin={{ top: 4, right: 4, left: -12, bottom: 0 }} barCategoryGap="28%">
              <XAxis dataKey="year" tick={{ fontSize: 10, fill: "var(--muted)" }} axisLine={false} tickLine={false} />
              <YAxis tickFormatter={dollarTick} tick={{ fontSize: 10, fill: "var(--muted)" }} axisLine={false} tickLine={false} width={40} />
              <Tooltip content={<CustomTooltip unit="$B" />} cursor={{ fill: "rgba(255,255,255,0.04)" }} />
              <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                {revenue.map((_, i) => (
                  <Cell key={i} fill={i === revenue.length - 1 ? BLUE : `${BLUE}80`} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <div className="h-36 flex items-center justify-center text-xs" style={{ color: "var(--muted)" }}>No data</div>
        )}
      </ChartCard>

      {/* ── Free Cash Flow ── */}
      <ChartCard title="Free Cash Flow (Annual)" subtitle="Operating CF minus CapEx, in $B — fiscal year">
        {fcf.length ? (
          <ResponsiveContainer width="100%" height={160}>
            <BarChart data={fcf} margin={{ top: 4, right: 4, left: -12, bottom: 0 }} barCategoryGap="28%">
              <XAxis dataKey="year" tick={{ fontSize: 10, fill: "var(--muted)" }} axisLine={false} tickLine={false} />
              <YAxis tickFormatter={dollarTick} tick={{ fontSize: 10, fill: "var(--muted)" }} axisLine={false} tickLine={false} width={40} />
              <Tooltip content={<CustomTooltip unit="$B" />} cursor={{ fill: "rgba(255,255,255,0.04)" }} />
              <ReferenceLine y={0} stroke={MUTED} strokeDasharray="3 3" />
              <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                {fcf.map((d, i) => (
                  <Cell
                    key={i}
                    fill={d.value < 0 ? (i === fcf.length - 1 ? RED : `${RED}80`) : (i === fcf.length - 1 ? GREEN : `${GREEN}80`)}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <div className="h-36 flex items-center justify-center text-xs" style={{ color: "var(--muted)" }}>No data</div>
        )}
      </ChartCard>

      {/* ── P/E History ── */}
      <ChartCard title="P/E Ratio History" subtitle="Price ÷ diluted EPS at fiscal year-end + current TTM">
        {peHistory.length ? (
          <ResponsiveContainer width="100%" height={160}>
            <BarChart data={peHistory} margin={{ top: 4, right: 4, left: -12, bottom: 0 }} barCategoryGap="28%">
              <XAxis dataKey="year" tick={{ fontSize: 10, fill: "var(--muted)" }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 10, fill: "var(--muted)" }} axisLine={false} tickLine={false} width={36} />
              <Tooltip content={<CustomTooltip unit="x" />} cursor={{ fill: "rgba(255,255,255,0.04)" }} />
              <Bar dataKey="pe" radius={[4, 4, 0, 0]}>
                {peHistory.map((_, i) => (
                  <Cell
                    key={i}
                    fill={i === peHistory.length - 1 ? AMBER : `${AMBER}80`}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <div className="h-36 flex items-center justify-center text-xs" style={{ color: "var(--muted)" }}>No data</div>
        )}
      </ChartCard>

    </div>
  );
}
