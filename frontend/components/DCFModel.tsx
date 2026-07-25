"use client";

import { useEffect, useState } from "react";
import { RefreshCw, TrendingUp, TrendingDown, Minus } from "lucide-react";
import { API_BASE } from "@/lib/api";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, ReferenceLine,
} from "recharts";

interface DCFData {
  ticker: string;
  price: number;
  fcfTtm: number;
  netDebtB: number;
  sharesB: number;
  assumptions: {
    wacc: number; costOfEquity: number; costOfDebt: number;
    beta: number; riskFreeRate: number; taxRate: number;
    weightEquity: number; weightDebt: number;
  };
  historicalCagr: number | null;
  fcfHistory: { year: number; fcf: number }[];
  scenarios: {
    bear: ScenarioData; base: ScenarioData; bull: ScenarioData;
  };
  sensitivity: {
    waccRates: number[]; termRates: number[]; grid: (number | null)[][];
  };
}

interface ScenarioData {
  growthRate: number; terminalGrowth: number;
  pvFcfs: number; pvTerminal: number; totalPv: number;
  intrinsicValue: number; upside: number;
  projections: { year: string; fcf: number; pv: number }[];
}

function fmt(v: number | null | undefined, d = 2) {
  if (v == null) return "N/A";
  return v.toFixed(d);
}

function UpsideBadge({ upside }: { upside: number }) {
  const positive = upside >= 0;
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold"
      style={{
        background: positive ? "rgba(34,197,94,0.1)" : "rgba(239,68,68,0.1)",
        color: positive ? "#22c55e" : "#ef4444",
        border: `1px solid ${positive ? "rgba(34,197,94,0.2)" : "rgba(239,68,68,0.2)"}`,
      }}>
      {positive ? <TrendingUp size={10} /> : <TrendingDown size={10} />}
      {positive ? "+" : ""}{upside.toFixed(1)}%
    </span>
  );
}

function ScenarioCard({ label, color, data, price }: {
  label: string; color: string; data: ScenarioData; price: number;
}) {
  return (
    <div className="rounded-xl p-4 flex flex-col gap-3"
      style={{ background: "var(--surface2)", border: `1px solid ${color}30`, borderTop: `2px solid ${color}` }}>
      <div className="flex items-center justify-between">
        <span className="text-xs font-bold uppercase tracking-widest" style={{ color }}>{label}</span>
        <UpsideBadge upside={data.upside} />
      </div>

      <div className="flex items-end gap-2">
        <span className="text-3xl font-extrabold tabular-nums" style={{ color: "var(--text)" }}>
          ${fmt(data.intrinsicValue)}
        </span>
        <span className="text-xs mb-1" style={{ color: "var(--muted)" }}>
          vs ${price.toFixed(2)} current
        </span>
      </div>

      <div className="grid grid-cols-2 gap-2 text-xs">
        <div className="flex flex-col gap-0.5">
          <span style={{ color: "var(--muted)" }}>FCF growth / yr</span>
          <span className="font-semibold" style={{ color: "var(--text)" }}>{data.growthRate}%</span>
        </div>
        <div className="flex flex-col gap-0.5">
          <span style={{ color: "var(--muted)" }}>Terminal growth</span>
          <span className="font-semibold" style={{ color: "var(--text)" }}>{data.terminalGrowth}%</span>
        </div>
        <div className="flex flex-col gap-0.5">
          <span style={{ color: "var(--muted)" }}>PV of FCFs</span>
          <span className="font-semibold" style={{ color: "var(--text)" }}>${fmt(data.pvFcfs)}B</span>
        </div>
        <div className="flex flex-col gap-0.5">
          <span style={{ color: "var(--muted)" }}>PV terminal value</span>
          <span className="font-semibold" style={{ color: "var(--text)" }}>${fmt(data.pvTerminal)}B</span>
        </div>
      </div>

      {/* Mini 5-year projection table */}
      <div className="rounded-lg overflow-hidden border" style={{ borderColor: "var(--border)" }}>
        <table className="w-full text-xs">
          <thead>
            <tr style={{ background: "var(--surface)" }}>
              {["Year", "FCF ($B)", "PV ($B)"].map(h => (
                <th key={h} className="px-2 py-1.5 text-left font-semibold uppercase tracking-wider"
                  style={{ color: "var(--muted2)" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.projections.map((row, i) => (
              <tr key={row.year} style={{ background: i % 2 === 0 ? "transparent" : "rgba(255,255,255,0.02)" }}>
                <td className="px-2 py-1.5 font-medium" style={{ color: "var(--muted2)" }}>{row.year}</td>
                <td className="px-2 py-1.5 tabular-nums" style={{ color: "var(--text)" }}>{row.fcf.toFixed(1)}</td>
                <td className="px-2 py-1.5 tabular-nums" style={{ color: "var(--muted2)" }}>{row.pv.toFixed(1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function DCFModel({ ticker }: { ticker: string }) {
  const [data, setData]       = useState<DCFData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState<string | null>(null);

  async function load() {
    setLoading(true); setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/stock/${ticker}/dcf-data`);
      if (!res.ok) {
        const j = await res.json();
        throw new Error(j.detail || "Failed");
      }
      setData(await res.json());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { setData(null); setError(null); }, [ticker]);
  useEffect(() => { load(); }, [ticker]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-48 gap-3">
        <RefreshCw size={18} className="animate-spin" style={{ color: "var(--blue)" }} />
        <span className="text-sm" style={{ color: "var(--muted2)" }}>Computing DCF model…</span>
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

  const { assumptions: a, sensitivity: sens } = data;
  const baseIV = data.scenarios.base.intrinsicValue;

  return (
    <div className="flex flex-col gap-5">

      {/* Header */}
      <div className="rounded-xl px-5 py-4 flex items-center justify-between"
        style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
        <div>
          <div className="text-sm font-bold" style={{ color: "var(--text)" }}>
            DCF Valuation — {ticker}
          </div>
          <div className="text-xs mt-0.5" style={{ color: "var(--muted)" }}>
            5-year FCF projection · Gordon Growth terminal value · All numbers from live yfinance data
          </div>
        </div>
        <div className="flex items-center gap-3">
          <div className="text-right">
            <div className="text-xs" style={{ color: "var(--muted)" }}>Base intrinsic value</div>
            <div className="text-2xl font-extrabold tabular-nums" style={{ color: "var(--text)" }}>
              ${fmt(baseIV)}
            </div>
          </div>
          <UpsideBadge upside={data.scenarios.base.upside} />
          <button onClick={load}
            className="w-8 h-8 flex items-center justify-center rounded-lg hover:opacity-80 transition-opacity"
            style={{ background: "var(--surface2)", border: "1px solid var(--border2)", color: "var(--muted2)" }}>
            <RefreshCw size={13} />
          </button>
        </div>
      </div>

      {/* WACC assumptions */}
      <div className="rounded-xl p-4"
        style={{ background: "var(--surface)", border: "1px solid var(--border)", borderTop: "2px solid #f59e0b" }}>
        <div className="text-xs font-bold uppercase tracking-widest mb-3" style={{ color: "#f59e0b" }}>
          WACC Assumptions
        </div>
        <div className="grid grid-cols-4 gap-x-6 gap-y-3 text-xs">
          {[
            ["WACC",          `${a.wacc}%`],
            ["Cost of Equity",`${a.costOfEquity}%`],
            ["Cost of Debt",  `${a.costOfDebt}%`],
            ["Beta",          a.beta.toFixed(2)],
            ["Risk-Free Rate",`${a.riskFreeRate}% (10Y UST)`],
            ["Tax Rate",      `${a.taxRate}%`],
            ["Equity Weight", `${a.weightEquity}%`],
            ["Debt Weight",   `${a.weightDebt}%`],
          ].map(([label, val]) => (
            <div key={String(label)} className="flex flex-col gap-0.5">
              <span style={{ color: "var(--muted)" }}>{label}</span>
              <span className="font-semibold tabular-nums" style={{ color: "var(--text)" }}>{val}</span>
            </div>
          ))}
        </div>
        {data.historicalCagr !== null && (
          <div className="mt-3 pt-3 border-t text-xs" style={{ borderColor: "var(--border)" }}>
            <span style={{ color: "var(--muted)" }}>Historical FCF CAGR: </span>
            <span className="font-semibold" style={{ color: "var(--text)" }}>{data.historicalCagr}%</span>
            <span className="ml-2" style={{ color: "var(--muted)" }}>
              (growth scenarios are capped below this to be conservative)
            </span>
          </div>
        )}
      </div>

      {/* FCF history chart */}
      {data.fcfHistory.length >= 2 && (
        <div className="rounded-xl p-4" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
          <div className="text-xs font-bold uppercase tracking-widest mb-3" style={{ color: "var(--muted2)" }}>
            Annual FCF History ($B)
          </div>
          <ResponsiveContainer width="100%" height={120}>
            <BarChart data={data.fcfHistory} barCategoryGap="35%">
              <XAxis dataKey="year" tick={{ fill: "var(--muted)", fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: "var(--muted)", fontSize: 11 }} axisLine={false} tickLine={false} width={40}
                tickFormatter={v => `$${v}B`} />
              <Tooltip
                contentStyle={{ background: "var(--surface2)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 }}
                formatter={(v) => [`$${Number(v).toFixed(1)}B`, "FCF"]}
                labelStyle={{ color: "var(--muted2)" }}
              />
              <Bar dataKey="fcf" radius={[4, 4, 0, 0]}>
                {data.fcfHistory.map((_, i) => (
                  <Cell key={i} fill={i === data.fcfHistory.length - 1 ? "#3b82f6" : "#3b82f640"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Three scenario cards */}
      <div className="grid grid-cols-3 gap-4">
        <ScenarioCard label="Bear Case"  color="#ef4444" data={data.scenarios.bear} price={data.price} />
        <ScenarioCard label="Base Case"  color="#3b82f6" data={data.scenarios.base} price={data.price} />
        <ScenarioCard label="Bull Case"  color="#22c55e" data={data.scenarios.bull} price={data.price} />
      </div>

      {/* Sensitivity table */}
      <div className="rounded-xl p-4" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
        <div className="text-xs font-bold uppercase tracking-widest mb-1" style={{ color: "var(--muted2)" }}>
          Sensitivity: Intrinsic Value vs WACC & Terminal Growth
        </div>
        <div className="text-xs mb-3" style={{ color: "var(--muted)" }}>
          Uses base-case FCF growth rate of {data.scenarios.base.growthRate}% · current price ${data.price.toFixed(2)}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs border-collapse">
            <thead>
              <tr>
                <th className="px-3 py-2 text-left font-semibold" style={{ color: "var(--muted2)", background: "var(--surface2)" }}>
                  WACC ↓ / Term.g →
                </th>
                {sens.termRates.map(tg => (
                  <th key={tg} className="px-3 py-2 text-center font-semibold"
                    style={{ color: "var(--muted2)", background: "var(--surface2)" }}>
                    {tg}%
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sens.grid.map((row, wi) => (
                <tr key={wi}>
                  <td className="px-3 py-2 font-semibold" style={{ color: "var(--muted2)", background: "var(--surface2)" }}>
                    {sens.waccRates[wi]}%
                  </td>
                  {row.map((iv, ti) => {
                    const abovePrice = iv !== null && iv > data.price * 1.05;
                    const belowPrice = iv !== null && iv < data.price * 0.95;
                    const isBase     = wi === 2 && ti === 2;
                    return (
                      <td key={ti} className="px-3 py-2 text-center tabular-nums font-medium"
                        style={{
                          color: abovePrice ? "#22c55e" : belowPrice ? "#ef4444" : "var(--muted2)",
                          background: isBase ? "rgba(59,130,246,0.1)" : "transparent",
                          border: isBase ? "1px solid rgba(59,130,246,0.3)" : "1px solid transparent",
                          borderRadius: isBase ? 4 : 0,
                        }}>
                        {iv != null ? `$${iv.toFixed(0)}` : "—"}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="mt-2 flex items-center gap-4 text-xs" style={{ color: "var(--muted)" }}>
          <span><span style={{ color: "#22c55e" }}>Green</span> = above current price</span>
          <span><span style={{ color: "#ef4444" }}>Red</span> = below current price</span>
          <span><span style={{ color: "#3b82f6" }}>Blue cell</span> = base case</span>
        </div>
      </div>

    </div>
  );
}
