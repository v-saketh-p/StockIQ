"use client";

import { useEffect, useState, useRef } from "react";
import {
  TrendingUp, TrendingDown, Plus, Trash2, RefreshCw, X, Check,
} from "lucide-react";
import PortfolioPerformance from "./PortfolioPerformance";

export interface Position {
  ticker:       string;
  shares:       number;
  avgCost:      number;
  purchaseDate?: string;  // "YYYY-MM-DD"
}

interface LivePrice {
  price:     number;
  prevClose: number;
  changePct: number;
  name:      string;
}

interface Props {
  onSelectTicker: (t: string) => void;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function fmtMoney(v: number) {
  const abs = Math.abs(v);
  if (abs >= 1e9) return `$${(v / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `$${(v / 1e6).toFixed(2)}M`;
  if (abs >= 1e3) return `$${(v / 1e3).toFixed(1)}K`;
  return `$${v.toFixed(2)}`;
}

function pctColor(v: number) {
  return v > 0 ? "#22c55e" : v < 0 ? "#ef4444" : "var(--muted2)";
}

function SummaryCard({
  label, value, sub, positive,
}: { label: string; value: string; sub?: string; positive?: boolean | null }) {
  const color = positive == null ? "var(--text)" : positive ? "#22c55e" : "#ef4444";
  return (
    <div className="rounded-xl px-5 py-4 flex flex-col gap-1.5"
      style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
      <div className="text-xs uppercase tracking-widest font-semibold" style={{ color: "var(--muted)" }}>
        {label}
      </div>
      <div className="text-2xl font-extrabold tabular-nums" style={{ color }}>{value}</div>
      {sub && <div className="text-xs" style={{ color: "var(--muted)" }}>{sub}</div>}
    </div>
  );
}

// ── Add-position form ─────────────────────────────────────────────────────────

function AddForm({ onAdd, onCancel }: {
  onAdd: (ticker: string, shares: number, avgCost: number, date: string) => void;
  onCancel: () => void;
}) {
  const today = new Date().toISOString().split("T")[0];
  const [ticker,  setTicker]  = useState("");
  const [shares,  setShares]  = useState("");
  const [cost,    setCost]    = useState("");
  const [date,    setDate]    = useState(today);
  const [err,     setErr]     = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => { inputRef.current?.focus(); }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    const t  = ticker.trim().toUpperCase();
    const sh = parseFloat(shares);
    const ac = parseFloat(cost);
    if (!t)                    return setErr("Enter a ticker symbol");
    if (isNaN(sh) || sh <= 0)  return setErr("Shares must be a positive number");
    if (isNaN(ac) || ac <= 0)  return setErr("Avg cost must be a positive number");
    if (!date)                 return setErr("Select a purchase date");
    setLoading(true);
    try {
      const res = await fetch(`http://localhost:8000/api/portfolio/prices?tickers=${t}`);
      const json = await res.json();
      if (!json.prices[t]) return setErr(`Ticker "${t}" not found`);
      onAdd(t, sh, ac, date);
    } catch {
      setErr("Could not verify ticker — check your connection");
    } finally { setLoading(false); }
  }

  const inputClass = "rounded-lg px-3 py-2 text-sm font-medium outline-none transition-all w-full";
  const inputStyle = { background: "var(--surface2)", border: "1px solid var(--border2)", color: "var(--text)" };

  return (
    <form onSubmit={submit}
      className="rounded-xl p-4 flex flex-col gap-3"
      style={{ background: "var(--surface)", border: "1px solid var(--border)", borderTop: "2px solid #3b82f6" }}>
      <div className="text-sm font-bold" style={{ color: "var(--text)" }}>Add Position</div>

      <div className="grid grid-cols-4 gap-3">
        <div className="flex flex-col gap-1">
          <label className="text-xs font-semibold uppercase tracking-wider" style={{ color: "var(--muted)" }}>Ticker</label>
          <input ref={inputRef} type="text" value={ticker} placeholder="NVDA"
            onChange={e => setTicker(e.target.value.toUpperCase())}
            className={inputClass} style={inputStyle} />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs font-semibold uppercase tracking-wider" style={{ color: "var(--muted)" }}>Shares</label>
          <input type="number" value={shares} placeholder="10" step="any" min="0"
            onChange={e => setShares(e.target.value)}
            className={inputClass} style={inputStyle} />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs font-semibold uppercase tracking-wider" style={{ color: "var(--muted)" }}>Avg Cost</label>
          <input type="number" value={cost} placeholder="150.00" step="any" min="0"
            onChange={e => setCost(e.target.value)}
            className={inputClass} style={inputStyle} />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs font-semibold uppercase tracking-wider" style={{ color: "var(--muted)" }}>Purchase Date</label>
          <input type="date" value={date} max={today}
            onChange={e => setDate(e.target.value)}
            className={inputClass} style={inputStyle} />
        </div>
      </div>

      {err && (
        <div className="text-xs px-3 py-2 rounded-lg"
          style={{ background: "rgba(239,68,68,0.08)", color: "var(--red)", border: "1px solid rgba(239,68,68,0.2)" }}>
          {err}
        </div>
      )}

      <div className="flex gap-2">
        <button type="submit" disabled={loading}
          className="flex items-center gap-1.5 text-xs px-4 py-2 rounded-lg font-semibold transition-all hover:opacity-85 disabled:opacity-40"
          style={{ background: "linear-gradient(135deg,#3b82f6,#6366f1)", color: "#fff" }}>
          {loading ? <RefreshCw size={11} className="animate-spin" /> : <Check size={11} />}
          {loading ? "Verifying…" : "Add"}
        </button>
        <button type="button" onClick={onCancel}
          className="flex items-center gap-1.5 text-xs px-3 py-2 rounded-lg font-semibold transition-all hover:opacity-80"
          style={{ background: "var(--surface2)", border: "1px solid var(--border2)", color: "var(--muted2)" }}>
          <X size={11} /> Cancel
        </button>
      </div>
    </form>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function PortfolioTracker({ onSelectTicker }: Props) {
  const [positions, setPositions] = useState<Position[]>([]);
  const [prices,    setPrices]    = useState<Record<string, LivePrice>>({});
  const [loading,   setLoading]   = useState(false);
  const [showForm,  setShowForm]  = useState(false);
  const [confirmDel, setConfirmDel] = useState<string | null>(null);

  // Track whether we've finished the initial load so we don't overwrite
  // localStorage with the empty initial state before the load effect runs.
  const didLoad = useRef(false);

  // Load persisted positions on mount
  useEffect(() => {
    try {
      const saved = localStorage.getItem("portfolio_positions");
      if (saved) setPositions(JSON.parse(saved));
    } catch {}
    didLoad.current = true;
  }, []);

  // Save whenever positions change — but only after the initial load
  useEffect(() => {
    if (!didLoad.current) return;
    localStorage.setItem("portfolio_positions", JSON.stringify(positions));
  }, [positions]);

  async function fetchPrices(pos: Position[]) {
    if (!pos.length) { setPrices({}); return; }
    setLoading(true);
    try {
      const tickers = [...new Set(pos.map(p => p.ticker))].join(",");
      const res  = await fetch(`http://localhost:8000/api/portfolio/prices?tickers=${tickers}`);
      const json = await res.json();
      setPrices(json.prices ?? {});
    } catch {}
    finally { setLoading(false); }
  }

  useEffect(() => { fetchPrices(positions); }, [positions]);

  function addPosition(ticker: string, shares: number, avgCost: number, purchaseDate: string) {
    setPositions(prev => {
      const existing = prev.find(p => p.ticker === ticker);
      if (existing) {
        const totalShares = existing.shares + shares;
        const newAvg = (existing.shares * existing.avgCost + shares * avgCost) / totalShares;
        // Keep the earlier purchase date
        const earlierDate = existing.purchaseDate && existing.purchaseDate < purchaseDate
          ? existing.purchaseDate : purchaseDate;
        return prev.map(p =>
          p.ticker === ticker
            ? { ...p, shares: totalShares, avgCost: parseFloat(newAvg.toFixed(4)), purchaseDate: earlierDate }
            : p
        );
      }
      return [...prev, { ticker, shares, avgCost, purchaseDate }];
    });
    setShowForm(false);
  }

  function removePosition(ticker: string) {
    setPositions(prev => prev.filter(p => p.ticker !== ticker));
    setConfirmDel(null);
  }

  // ── Portfolio maths ──────────────────────────────────────────────────────
  const rows = positions.map(p => {
    const live      = prices[p.ticker];
    const mktValue  = live ? p.shares * live.price      : null;
    const costBasis = p.shares * p.avgCost;
    const pnl       = mktValue !== null ? mktValue - costBasis : null;
    const pnlPct    = pnl !== null ? (pnl / costBasis) * 100 : null;
    const todayPnl  = live ? p.shares * (live.price - live.prevClose) : null;
    return { ...p, live, mktValue, costBasis, pnl, pnlPct, todayPnl };
  });

  const totalValue    = rows.reduce((s, r) => s + (r.mktValue ?? 0), 0);
  const totalCost     = rows.reduce((s, r) => s + r.costBasis, 0);
  const totalPnl      = totalValue - totalCost;
  const totalPnlPct   = totalCost > 0 ? (totalPnl / totalCost) * 100 : 0;
  const todayTotal    = rows.reduce((s, r) => s + (r.todayPnl ?? 0), 0);
  const todayPct      = totalValue > 0 ? (todayTotal / (totalValue - todayTotal)) * 100 : 0;

  return (
    <div className="flex flex-col gap-5">

      {/* ── Page header ── */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-extrabold" style={{ color: "var(--text)" }}>Portfolio</h2>
          <p className="text-xs mt-0.5" style={{ color: "var(--muted)" }}>
            {positions.length} position{positions.length !== 1 ? "s" : ""} · live prices via yfinance
          </p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => fetchPrices(positions)} disabled={loading}
            className="w-8 h-8 flex items-center justify-center rounded-lg transition-all hover:opacity-80 disabled:opacity-40"
            style={{ background: "var(--surface2)", border: "1px solid var(--border2)", color: "var(--muted2)" }}>
            <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
          </button>
          <button onClick={() => setShowForm(v => !v)}
            className="flex items-center gap-1.5 text-xs px-3.5 py-2 rounded-lg font-semibold transition-all hover:opacity-85"
            style={{ background: "linear-gradient(135deg,#3b82f6,#6366f1)", color: "#fff" }}>
            <Plus size={13} /> Add Position
          </button>
        </div>
      </div>

      {/* ── Add form ── */}
      {showForm && (
        <AddForm onAdd={addPosition} onCancel={() => setShowForm(false)} />
      )}

      {/* ── Summary cards ── */}
      {positions.length > 0 && (
        <div className="grid grid-cols-4 gap-3">
          <SummaryCard
            label="Portfolio Value"
            value={fmtMoney(totalValue)}
            sub={`${positions.length} position${positions.length !== 1 ? "s" : ""}`}
            positive={null}
          />
          <SummaryCard
            label="Total Invested"
            value={fmtMoney(totalCost)}
            positive={null}
          />
          <SummaryCard
            label="Total P&L"
            value={`${totalPnl >= 0 ? "+" : ""}${fmtMoney(totalPnl)}`}
            sub={`${totalPnlPct >= 0 ? "+" : ""}${totalPnlPct.toFixed(2)}% all time`}
            positive={totalPnl >= 0}
          />
          <SummaryCard
            label="Today's P&L"
            value={`${todayTotal >= 0 ? "+" : ""}${fmtMoney(todayTotal)}`}
            sub={`${todayPct >= 0 ? "+" : ""}${todayPct.toFixed(2)}% today`}
            positive={todayTotal >= 0}
          />
        </div>
      )}

      {/* ── Empty state ── */}
      {positions.length === 0 && !showForm && (
        <div className="flex flex-col items-center justify-center py-20 gap-5"
          style={{ border: "1px dashed var(--border)", borderRadius: 16 }}>
          <div className="w-14 h-14 rounded-2xl flex items-center justify-center"
            style={{ background: "rgba(59,130,246,0.1)", border: "1px solid rgba(59,130,246,0.2)" }}>
            <TrendingUp size={24} style={{ color: "#3b82f6" }} />
          </div>
          <div className="text-center">
            <div className="font-bold text-sm" style={{ color: "var(--text)" }}>No positions yet</div>
            <div className="text-xs mt-1" style={{ color: "var(--muted)" }}>
              Add a position to start tracking your portfolio
            </div>
          </div>
          <button onClick={() => setShowForm(true)}
            className="flex items-center gap-1.5 text-xs px-4 py-2.5 rounded-xl font-semibold transition-all hover:opacity-85"
            style={{ background: "linear-gradient(135deg,#3b82f6,#6366f1)", color: "#fff" }}>
            <Plus size={13} /> Add your first position
          </button>
        </div>
      )}

      {/* ── Performance chart ── */}
      {positions.length > 0 && (
        <PortfolioPerformance positions={positions} />
      )}

      {/* ── Holdings table ── */}
      {rows.length > 0 && (
        <div className="rounded-xl overflow-hidden"
          style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>

          {/* Allocation bar */}
          {totalValue > 0 && (
            <div className="px-5 pt-4 pb-2">
              <div className="text-xs font-semibold uppercase tracking-wider mb-2" style={{ color: "var(--muted)" }}>
                Allocation
              </div>
              <div className="flex rounded-full overflow-hidden h-2 gap-px">
                {rows
                  .filter(r => r.mktValue != null && r.mktValue > 0)
                  .sort((a, b) => (b.mktValue ?? 0) - (a.mktValue ?? 0))
                  .map((r, i) => {
                    const colors = ["#3b82f6","#8b5cf6","#22c55e","#f59e0b","#ec4899","#06b6d4","#f97316","#a855f7"];
                    const w = ((r.mktValue ?? 0) / totalValue * 100).toFixed(1);
                    return (
                      <div key={r.ticker} title={`${r.ticker}: ${w}%`}
                        style={{ width: `${w}%`, background: colors[i % colors.length] }} />
                    );
                  })}
              </div>
              <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2">
                {rows
                  .filter(r => r.mktValue != null)
                  .sort((a, b) => (b.mktValue ?? 0) - (a.mktValue ?? 0))
                  .map((r, i) => {
                    const colors = ["#3b82f6","#8b5cf6","#22c55e","#f59e0b","#ec4899","#06b6d4","#f97316","#a855f7"];
                    const w = ((r.mktValue ?? 0) / totalValue * 100).toFixed(1);
                    return (
                      <div key={r.ticker} className="flex items-center gap-1 text-xs">
                        <span className="w-2 h-2 rounded-full" style={{ background: colors[i % colors.length] }} />
                        <span style={{ color: "var(--muted2)" }}>{r.ticker}</span>
                        <span style={{ color: "var(--muted)" }}>{w}%</span>
                      </div>
                    );
                  })}
              </div>
            </div>
          )}

          <div className="overflow-x-auto mt-3">
            <table className="w-full text-xs border-collapse">
              <thead>
                <tr style={{ background: "var(--surface2)", borderBottom: "1px solid var(--border)" }}>
                  {["Ticker / Name","Shares","Avg Cost","Current","Mkt Value","P&L","P&L %","Today",""].map(h => (
                    <th key={h} className="px-4 py-3 text-left font-semibold uppercase tracking-wider"
                      style={{ color: "var(--muted2)" }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row, i) => (
                  <tr key={row.ticker}
                    style={{ background: i % 2 === 0 ? "transparent" : "rgba(255,255,255,0.015)",
                             borderBottom: "1px solid var(--border)" }}>

                    {/* Ticker */}
                    <td className="px-4 py-3">
                      <button onClick={() => onSelectTicker(row.ticker)}
                        className="flex flex-col hover:opacity-80 transition-opacity text-left">
                        <span className="font-bold" style={{ color: "#3b82f6" }}>{row.ticker}</span>
                        <span className="text-[11px] truncate max-w-[130px]" style={{ color: "var(--muted)" }}>
                          {row.live?.name ?? "—"}
                        </span>
                      </button>
                    </td>

                    {/* Shares */}
                    <td className="px-4 py-3 tabular-nums" style={{ color: "var(--text)" }}>
                      {row.shares.toLocaleString(undefined, { maximumFractionDigits: 4 })}
                    </td>

                    {/* Avg Cost */}
                    <td className="px-4 py-3 tabular-nums" style={{ color: "var(--text)" }}>
                      ${row.avgCost.toFixed(2)}
                    </td>

                    {/* Current Price */}
                    <td className="px-4 py-3 tabular-nums font-semibold" style={{ color: "var(--text)" }}>
                      {row.live ? `$${row.live.price.toFixed(2)}` : (
                        <span style={{ color: "var(--muted)" }}>—</span>
                      )}
                    </td>

                    {/* Market Value */}
                    <td className="px-4 py-3 tabular-nums font-semibold" style={{ color: "var(--text)" }}>
                      {row.mktValue !== null ? fmtMoney(row.mktValue) : "—"}
                    </td>

                    {/* P&L $ */}
                    <td className="px-4 py-3 tabular-nums font-semibold"
                      style={{ color: row.pnl !== null ? pctColor(row.pnl) : "var(--muted)" }}>
                      {row.pnl !== null
                        ? `${row.pnl >= 0 ? "+" : ""}${fmtMoney(row.pnl)}`
                        : "—"}
                    </td>

                    {/* P&L % */}
                    <td className="px-4 py-3 tabular-nums"
                      style={{ color: row.pnlPct !== null ? pctColor(row.pnlPct) : "var(--muted)" }}>
                      {row.pnlPct !== null ? (
                        <span className="flex items-center gap-1">
                          {row.pnlPct >= 0 ? <TrendingUp size={11} /> : <TrendingDown size={11} />}
                          {row.pnlPct >= 0 ? "+" : ""}{row.pnlPct.toFixed(2)}%
                        </span>
                      ) : "—"}
                    </td>

                    {/* Today */}
                    <td className="px-4 py-3 tabular-nums"
                      style={{ color: row.live ? pctColor(row.live.changePct) : "var(--muted)" }}>
                      {row.live ? (
                        <>
                          {row.live.changePct >= 0 ? "+" : ""}{row.live.changePct.toFixed(2)}%
                          <div style={{ color: "var(--muted)", fontSize: 10 }}>
                            {row.todayPnl !== null
                              ? `${row.todayPnl >= 0 ? "+" : ""}${fmtMoney(row.todayPnl)}`
                              : ""}
                          </div>
                        </>
                      ) : "—"}
                    </td>

                    {/* Delete */}
                    <td className="px-4 py-3">
                      {confirmDel === row.ticker ? (
                        <div className="flex items-center gap-1.5">
                          <button onClick={() => removePosition(row.ticker)}
                            className="text-[11px] px-2 py-1 rounded-md font-semibold hover:opacity-80"
                            style={{ background: "rgba(239,68,68,0.12)", color: "var(--red)" }}>
                            Remove
                          </button>
                          <button onClick={() => setConfirmDel(null)}
                            className="text-[11px] px-2 py-1 rounded-md hover:opacity-80"
                            style={{ color: "var(--muted2)" }}>
                            Cancel
                          </button>
                        </div>
                      ) : (
                        <button onClick={() => setConfirmDel(row.ticker)}
                          className="w-7 h-7 flex items-center justify-center rounded-lg opacity-40 hover:opacity-100 transition-opacity"
                          style={{ color: "var(--red)" }}>
                          <Trash2 size={13} />
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

    </div>
  );
}
