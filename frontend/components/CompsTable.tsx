"use client";

import { useEffect, useState } from "react";
import { RefreshCw, TrendingUp, TrendingDown } from "lucide-react";

interface CompsRow {
  ticker: string; name: string; marketCapB: number | null; price: number;
  fwdPE: number | null; evEbitda: number | null; evRevenue: number | null;
  revGrowth: number | null; opMargin: number | null; netMargin: number | null;
}

interface CompsData {
  ticker: string; industry: string;
  target: CompsRow; peers: CompsRow[];
  peerMedian: { fwdPE: number | null; evEbitda: number | null; evRevenue: number | null;
                revGrowth: number | null; opMargin: number | null; netMargin: number | null };
  implied: {
    byFwdPE?:    { impliedPrice: number; upside: number };
    byEVEBITDA?: { impliedPrice: number; upside: number };
    byEVRevenue?: { impliedPrice: number; upside: number };
  };
}

function cell(v: number | null, suffix = "", decimals = 1) {
  if (v == null) return <span style={{ color: "var(--muted)" }}>—</span>;
  return <>{v.toFixed(decimals)}{suffix}</>;
}

function vsMedian(val: number | null, median: number | null, higherIsBetter: boolean) {
  if (val == null || median == null) return null;
  const pct = (val / median - 1) * 100;
  const good = higherIsBetter ? pct > 5 : pct < -5;
  const bad  = higherIsBetter ? pct < -5 : pct > 5;
  return (
    <span className="text-[10px] ml-1" style={{ color: good ? "#22c55e" : bad ? "#ef4444" : "var(--muted)" }}>
      {pct > 0 ? "+" : ""}{pct.toFixed(0)}%
    </span>
  );
}

function ImpliedCard({ label, data, currentPrice, color }: {
  label: string; data: { impliedPrice: number; upside: number }; currentPrice: number; color: string;
}) {
  const positive = data.upside >= 0;
  return (
    <div className="rounded-xl p-4 flex flex-col gap-2"
      style={{ background: "var(--surface2)", border: `1px solid ${color}25`, borderTop: `2px solid ${color}` }}>
      <div className="text-xs font-bold uppercase tracking-wider" style={{ color }}>{label}</div>
      <div className="text-2xl font-extrabold tabular-nums" style={{ color: "var(--text)" }}>
        ${data.impliedPrice.toFixed(2)}
      </div>
      <div className="flex items-center gap-1.5 text-xs">
        <span style={{ color: "var(--muted)" }}>vs ${currentPrice.toFixed(2)}</span>
        <span className="flex items-center gap-0.5 font-semibold"
          style={{ color: positive ? "#22c55e" : "#ef4444" }}>
          {positive ? <TrendingUp size={11} /> : <TrendingDown size={11} />}
          {positive ? "+" : ""}{data.upside.toFixed(1)}%
        </span>
      </div>
    </div>
  );
}

export default function CompsTable({ ticker }: { ticker: string }) {
  const [data, setData]       = useState<CompsData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState<string | null>(null);

  async function load() {
    setLoading(true); setError(null);
    try {
      const res = await fetch(`http://localhost:8000/api/stock/${ticker}/comps-data`);
      if (!res.ok) { const j = await res.json(); throw new Error(j.detail || "Failed"); }
      setData(await res.json());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally { setLoading(false); }
  }

  useEffect(() => { setData(null); setError(null); }, [ticker]);
  useEffect(() => { load(); }, [ticker]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-48 gap-3">
        <RefreshCw size={18} className="animate-spin" style={{ color: "var(--blue)" }} />
        <span className="text-sm" style={{ color: "var(--muted2)" }}>Fetching peer data…</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-xl px-5 py-4 text-sm"
        style={{ background: "rgba(239,68,68,0.07)", border: "1px solid rgba(239,68,68,0.2)", color: "var(--red)" }}>
        {error}
      </div>
    );
  }

  if (!data) return null;

  const rows = [data.target, ...data.peers];
  const med  = data.peerMedian;
  const cols = [
    { key: "fwdPE",     label: "Fwd P/E",    suffix: "x",  decimals: 1, higherIsBetter: false },
    { key: "evEbitda",  label: "EV/EBITDA",   suffix: "x",  decimals: 1, higherIsBetter: false },
    { key: "evRevenue", label: "EV/Revenue",  suffix: "x",  decimals: 2, higherIsBetter: false },
    { key: "revGrowth", label: "Rev Growth",  suffix: "%",  decimals: 1, higherIsBetter: true  },
    { key: "opMargin",  label: "Op Margin",   suffix: "%",  decimals: 1, higherIsBetter: true  },
    { key: "netMargin", label: "Net Margin",  suffix: "%",  decimals: 1, higherIsBetter: true  },
  ] as const;

  return (
    <div className="flex flex-col gap-5">

      {/* Header */}
      <div className="rounded-xl px-5 py-4 flex items-center justify-between"
        style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
        <div>
          <div className="text-sm font-bold" style={{ color: "var(--text)" }}>
            Comparable Companies — {ticker}
          </div>
          <div className="text-xs mt-0.5" style={{ color: "var(--muted)" }}>
            Industry: {data.industry || "—"} · {data.peers.length} peers · All metrics live from yfinance
          </div>
        </div>
        <button onClick={load}
          className="w-8 h-8 flex items-center justify-center rounded-lg hover:opacity-80 transition-opacity"
          style={{ background: "var(--surface2)", border: "1px solid var(--border2)", color: "var(--muted2)" }}>
          <RefreshCw size={13} />
        </button>
      </div>

      {/* Implied value cards */}
      {Object.keys(data.implied).length > 0 && (
        <div className={`grid gap-4`}
          style={{ gridTemplateColumns: `repeat(${Object.keys(data.implied).length}, 1fr)` }}>
          {data.implied.byFwdPE && (
            <ImpliedCard label="Implied by Fwd P/E" data={data.implied.byFwdPE}
              currentPrice={data.target.price} color="#f59e0b" />
          )}
          {data.implied.byEVEBITDA && (
            <ImpliedCard label="Implied by EV/EBITDA" data={data.implied.byEVEBITDA}
              currentPrice={data.target.price} color="#8b5cf6" />
          )}
          {data.implied.byEVRevenue && (
            <ImpliedCard label="Implied by EV/Revenue" data={data.implied.byEVRevenue}
              currentPrice={data.target.price} color="#3b82f6" />
          )}
        </div>
      )}

      {/* Comparison table */}
      <div className="rounded-xl overflow-hidden"
        style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
        <div className="overflow-x-auto">
          <table className="w-full text-xs border-collapse">
            <thead>
              <tr style={{ background: "var(--surface2)" }}>
                <th className="px-4 py-3 text-left font-semibold sticky left-0"
                  style={{ color: "var(--muted2)", background: "var(--surface2)", minWidth: 160 }}>
                  Company
                </th>
                <th className="px-4 py-3 text-right font-semibold" style={{ color: "var(--muted2)" }}>Mkt Cap</th>
                {cols.map(c => (
                  <th key={c.key} className="px-4 py-3 text-right font-semibold" style={{ color: "var(--muted2)" }}>
                    {c.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => {
                const isTarget = row.ticker === ticker;
                return (
                  <tr key={row.ticker}
                    style={{
                      background: isTarget
                        ? "rgba(59,130,246,0.06)"
                        : i % 2 === 0 ? "transparent" : "rgba(255,255,255,0.015)",
                      borderLeft: isTarget ? "2px solid #3b82f6" : "2px solid transparent",
                    }}>
                    <td className="px-4 py-3 sticky left-0"
                      style={{ background: isTarget ? "rgba(59,130,246,0.06)" : "var(--surface)" }}>
                      <div className="font-bold" style={{ color: isTarget ? "#3b82f6" : "var(--text)" }}>
                        {row.ticker}
                        {isTarget && <span className="ml-1.5 text-[10px] font-normal" style={{ color: "var(--muted)" }}>◀ target</span>}
                      </div>
                      <div className="text-[11px] mt-0.5 truncate max-w-[140px]" style={{ color: "var(--muted)" }}>
                        {row.name}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums" style={{ color: "var(--text)" }}>
                      {row.marketCapB != null ? `$${row.marketCapB.toFixed(0)}B` : "—"}
                    </td>
                    {cols.map(c => (
                      <td key={c.key} className="px-4 py-3 text-right tabular-nums" style={{ color: "var(--text)" }}>
                        {cell(row[c.key], c.suffix, c.decimals)}
                        {isTarget && vsMedian(row[c.key], med[c.key], c.higherIsBetter)}
                      </td>
                    ))}
                  </tr>
                );
              })}

              {/* Peer median row */}
              <tr style={{ background: "rgba(255,255,255,0.04)", borderTop: "1px solid var(--border)" }}>
                <td className="px-4 py-3 font-bold sticky left-0"
                  style={{ background: "rgba(255,255,255,0.04)", color: "var(--muted2)" }}>
                  Peer Median
                </td>
                <td className="px-4 py-3" />
                {cols.map(c => (
                  <td key={c.key} className="px-4 py-3 text-right tabular-nums font-semibold"
                    style={{ color: "var(--muted2)" }}>
                    {cell(med[c.key], c.suffix, c.decimals)}
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
        <div className="px-4 py-2 border-t text-[11px]" style={{ borderColor: "var(--border)", color: "var(--muted)" }}>
          Colored % next to target metrics = premium (+) or discount (−) vs peer median
        </div>
      </div>

    </div>
  );
}
