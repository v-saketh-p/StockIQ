"use client";

import { useEffect, useState, useRef, useMemo } from "react";
import {
  TrendingUp, TrendingDown, Plus, Trash2, RefreshCw, X, Check, Upload,
} from "lucide-react";
import PortfolioPerformance from "./PortfolioPerformance";

export interface Position {
  ticker:       string;
  shares:       number;
  avgCost:      number;
  purchaseDate?: string;  // earliest buy date
}

export interface Transaction {
  id:       string;   // stable dedup key
  ticker:   string;
  date:     string;   // YYYY-MM-DD
  shares:   number;
  price:    number;   // per share in native currency
  currency: string;   // "USD", "GBP", "GBX", …
  type:     "buy" | "sell";
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

function fmtMoney(v: number, sym = "$") {
  const abs = Math.abs(v);
  if (abs >= 1e9) return `${sym}${(v / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${sym}${(v / 1e6).toFixed(2)}M`;
  if (abs >= 1e3) return `${sym}${(v / 1e3).toFixed(1)}K`;
  return `${sym}${v.toFixed(2)}`;
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

function parseCSVRow(line: string): string[] {
  const fields: string[] = [];
  let current = "";
  let inQuotes = false;
  for (const ch of line) {
    if (ch === '"') { inQuotes = !inQuotes; }
    else if (ch === ',' && !inQuotes) { fields.push(current); current = ""; }
    else { current += ch; }
  }
  fields.push(current);
  return fields;
}

function parseT212CSV(text: string): Transaction[] {
  const lines = text.split("\n").filter(l => l.trim());
  if (!lines.length) return [];

  const headers = parseCSVRow(lines[0]).map(h => h.replace(/^"|"$/g, "").trim());
  const col = (row: string[], name: string) => {
    const i = headers.indexOf(name);
    return i >= 0 ? (row[i] ?? "").replace(/^"|"$/g, "").trim() : "";
  };

  const txns: Transaction[] = [];
  for (let i = 1; i < lines.length; i++) {
    const row    = parseCSVRow(lines[i]);
    const action = col(row, "Action");
    const ticker = col(row, "Ticker");
    if (!ticker) continue;

    const isBuy  = /buy/i.test(action);
    const isSell = /sell/i.test(action);
    if (!isBuy && !isSell) continue;

    const shares   = parseFloat(col(row, "No. of shares").replace(/,/g, "")) || 0;
    const price    = parseFloat(col(row, "Price / share").replace(/,/g, "")) || 0;
    const date     = col(row, "Time").slice(0, 10);
    const currency = col(row, "Currency (Price / share)") || "USD";
    // Use T212's own transaction ID when available — best dedup key
    const t212id   = col(row, "ID");
    if (!shares || !price || !date) continue;

    const id = t212id || `${ticker}-${date}-${shares.toFixed(6)}-${price.toFixed(4)}`;
    txns.push({ id, ticker, date, shares, price, currency, type: isBuy ? "buy" : "sell" });
  }
  return txns;
}

function derivePositions(txns: Transaction[]): Position[] {
  const acc: Record<string, { shares: number; costUsd: number; firstDate: string | null }> = {};
  for (const t of [...txns].sort((a, b) => a.date.localeCompare(b.date))) {
    if (!acc[t.ticker]) acc[t.ticker] = { shares: 0, costUsd: 0, firstDate: null };
    if (t.type === "buy") {
      acc[t.ticker].shares  += t.shares;
      acc[t.ticker].costUsd += t.shares * t.price;
      if (!acc[t.ticker].firstDate) acc[t.ticker].firstDate = t.date;
    } else {
      const frac = acc[t.ticker].shares > 0 ? t.shares / acc[t.ticker].shares : 0;
      acc[t.ticker].shares  -= t.shares;
      acc[t.ticker].costUsd -= acc[t.ticker].costUsd * frac;
    }
  }
  return Object.entries(acc)
    .filter(([, p]) => p.shares > 0.0001)
    .map(([ticker, p]) => ({
      ticker,
      shares:       parseFloat(p.shares.toFixed(6)),
      avgCost:      parseFloat((p.costUsd / p.shares).toFixed(4)),
      purchaseDate: p.firstDate ?? undefined,
    }));
}

export default function PortfolioTracker({ onSelectTicker }: Props) {
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [prices,       setPrices]       = useState<Record<string, LivePrice>>({});
  const [loading,      setLoading]      = useState(false);
  const [showForm,     setShowForm]     = useState(false);
  const [confirmDel,   setConfirmDel]   = useState<string | null>(null);
  const [importMsg,    setImportMsg]    = useState<string | null>(null);
  const [currency,     setCurrency]     = useState<"USD" | "GBP">("USD");
  const [usdToGbp,     setUsdToGbp]     = useState(0.79);
  const [sortBy,       setSortBy]       = useState<"value" | "pnlPct" | "todayPct">("value");
  const [sortDir,      setSortDir]      = useState<"desc" | "asc">("desc");
  const fileRef = useRef<HTMLInputElement>(null);

  const [isLoaded,        setIsLoaded]        = useState(false);
  const [netDeposits,     setNetDeposits]     = useState<number | null>(2805.60);
  const [depositsInput,   setDepositsInput]   = useState("");
  const [editingDeposits, setEditingDeposits] = useState(false);

  // Derive positions from transactions (for display, price fetching, backend calls)
  const positions = useMemo(() => derivePositions(transactions), [transactions]);

  // Load persisted state on mount; migrate old positions format if needed
  useEffect(() => {
    try {
      const savedTxns = localStorage.getItem("portfolio_transactions");
      if (savedTxns) {
        setTransactions(JSON.parse(savedTxns));
      } else {
        // Migrate from old single-position-per-ticker format
        const oldPos = localStorage.getItem("portfolio_positions");
        if (oldPos) {
          const parsed: Position[] = JSON.parse(oldPos);
          setTransactions(parsed.map(p => ({
            id:       `${p.ticker}-${p.purchaseDate ?? "2025-01-01"}-legacy`,
            ticker:   p.ticker,
            date:     p.purchaseDate ?? "2025-01-01",
            shares:   p.shares,
            price:    p.avgCost,
            currency: "USD",
            type:     "buy" as const,
          })));
        }
      }
      const savedDeps = localStorage.getItem("portfolio_net_deposits");
      if (savedDeps) setNetDeposits(parseFloat(savedDeps));
    } catch {}
    setIsLoaded(true);
  }, []);

  useEffect(() => {
    if (!isLoaded) return;
    localStorage.setItem("portfolio_transactions", JSON.stringify(transactions));
  }, [transactions, isLoaded]);

  useEffect(() => {
    if (!isLoaded) return;
    if (netDeposits != null) localStorage.setItem("portfolio_net_deposits", String(netDeposits));
  }, [netDeposits, isLoaded]);

  // Fetch live USD→GBP rate, refresh every 60 seconds
  useEffect(() => {
    async function fetchFx() {
      try {
        const res  = await fetch("http://localhost:8000/api/fx/usdgbp");
        const json = await res.json();
        if (json.usdToGbp) setUsdToGbp(json.usdToGbp);
      } catch {}
    }
    fetchFx();
    const id = setInterval(fetchFx, 60_000);
    return () => clearInterval(id);
  }, []);

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

  function addPosition(ticker: string, shares: number, avgCost: number, date: string) {
    const id = `${ticker}-${date}-${shares.toFixed(6)}-${avgCost.toFixed(4)}`;
    setTransactions(prev => [...prev, { id, ticker, date, shares, price: avgCost, currency: "USD", type: "buy" }]);
    setShowForm(false);
  }

  function removePosition(ticker: string) {
    setTransactions(prev => prev.filter(t => t.ticker !== ticker));
    setConfirmDel(null);
  }

  function handleImport(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = "";
    const reader = new FileReader();
    reader.onload = (ev) => {
      const text = ev.target?.result as string;
      const imported = parseT212CSV(text);
      if (!imported.length) { setImportMsg("No transactions found in CSV."); return; }
      setTransactions(prev => {
        const existingIds = new Set(prev.map(t => t.id));
        const newTxns = imported.filter(t => !existingIds.has(t.id));
        return [...prev, ...newTxns];
      });
      const tickers = new Set(imported.map(t => t.ticker));
      setImportMsg(`Imported ${imported.length} transactions across ${tickers.size} tickers`);
      setTimeout(() => setImportMsg(null), 4000);
    };
    reader.readAsText(file);
  }

  // ── Currency helpers ────────────────────────────────────────────────────
  const sym  = currency === "GBP" ? "£" : "$";
  const conv = (usd: number) => currency === "GBP" ? usd * usdToGbp : usd;
  const fmt  = (usd: number) => fmtMoney(conv(usd), sym);

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
  const todayTotal    = rows.reduce((s, r) => s + (r.todayPnl ?? 0), 0);
  const todayPct      = totalValue > 0 ? (todayTotal / (totalValue - todayTotal)) * 100 : 0;

  // P&L vs net deposits (converted to USD for consistent arithmetic with totalValue)
  const netDepositsUsd = netDeposits != null && usdToGbp > 0 ? netDeposits / usdToGbp : null;
  const totalPnl    = netDepositsUsd != null ? totalValue - netDepositsUsd : totalValue - totalCost;
  const totalPnlPct = netDepositsUsd != null && netDepositsUsd > 0
    ? (totalPnl / netDepositsUsd) * 100
    : totalCost > 0 ? ((totalValue - totalCost) / totalCost) * 100 : 0;

  const sortedRows = [...rows].sort((a, b) => {
    let av = 0, bv = 0;
    if (sortBy === "value")    { av = a.mktValue ?? 0;          bv = b.mktValue ?? 0; }
    if (sortBy === "pnlPct")   { av = a.pnlPct ?? -Infinity;    bv = b.pnlPct ?? -Infinity; }
    if (sortBy === "todayPct") { av = a.live?.changePct ?? -Infinity; bv = b.live?.changePct ?? -Infinity; }
    return sortDir === "desc" ? bv - av : av - bv;
  });

  function heatmapBg(changePct: number | undefined) {
    if (changePct == null) return "rgba(100,100,120,0.12)";
    const intensity = Math.min(Math.abs(changePct) / 4, 1);
    const alpha = 0.18 + intensity * 0.65;
    return changePct > 0
      ? `rgba(22,163,74,${alpha.toFixed(2)})`
      : changePct < 0
      ? `rgba(220,38,38,${alpha.toFixed(2)})`
      : "rgba(100,100,120,0.12)";
  }

  function toggleSort(key: typeof sortBy) {
    if (sortBy === key) setSortDir(d => d === "desc" ? "asc" : "desc");
    else { setSortBy(key); setSortDir("desc"); }
  }

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
        <div className="flex gap-2 items-center">
          <button onClick={() => fetchPrices(positions)} disabled={loading}
            className="w-8 h-8 flex items-center justify-center rounded-lg transition-all hover:opacity-80 disabled:opacity-40"
            style={{ background: "var(--surface2)", border: "1px solid var(--border2)", color: "var(--muted2)" }}>
            <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
          </button>

          {/* Currency toggle */}
          <div className="flex rounded-lg overflow-hidden text-xs font-semibold"
            style={{ border: "1px solid var(--border2)" }}>
            {(["USD", "GBP"] as const).map(c => (
              <button key={c} onClick={() => setCurrency(c)}
                className="px-3 py-1.5 transition-all"
                style={{
                  background: currency === c ? "linear-gradient(135deg,#3b82f6,#6366f1)" : "var(--surface2)",
                  color:      currency === c ? "#fff" : "var(--muted2)",
                }}>
                {c === "USD" ? "$ USD" : "£ GBP"}
              </button>
            ))}
          </div>
          <input ref={fileRef} type="file" accept=".csv" className="hidden" onChange={handleImport} />
          {transactions.length > 0 && (
            <button
              onClick={() => {
                setTransactions([]);
                setImportMsg("Portfolio cleared — ready to import.");
                setTimeout(() => setImportMsg(null), 3000);
              }}
              className="flex items-center gap-1.5 text-xs px-3.5 py-2 rounded-lg font-semibold transition-all hover:opacity-85"
              style={{ background: "var(--surface2)", border: "1px solid rgba(239,68,68,0.4)", color: "var(--red)" }}>
              <Trash2 size={13} /> Clear All
            </button>
          )}
          <button onClick={() => fileRef.current?.click()}
            className="flex items-center gap-1.5 text-xs px-3.5 py-2 rounded-lg font-semibold transition-all hover:opacity-85"
            style={{ background: "var(--surface2)", border: "1px solid var(--border2)", color: "var(--muted2)" }}>
            <Upload size={13} /> Import CSV
          </button>
          <button onClick={() => setShowForm(v => !v)}
            className="flex items-center gap-1.5 text-xs px-3.5 py-2 rounded-lg font-semibold transition-all hover:opacity-85"
            style={{ background: "linear-gradient(135deg,#3b82f6,#6366f1)", color: "#fff" }}>
            <Plus size={13} /> Add Position
          </button>
        </div>
      </div>

      {/* ── Import banner ── */}
      {importMsg && (
        <div className="text-xs rounded-xl px-4 py-3 flex items-center gap-2"
          style={{ background: "rgba(34,197,94,0.08)", color: "#22c55e", border: "1px solid rgba(34,197,94,0.2)" }}>
          <Check size={13} /> {importMsg}
        </div>
      )}

      {/* ── Add form ── */}
      {showForm && (
        <AddForm onAdd={addPosition} onCancel={() => setShowForm(false)} />
      )}

      {/* ── Summary cards ── */}
      {positions.length > 0 && (
        <div className="grid grid-cols-4 gap-3">
          <SummaryCard
            label="Portfolio Value"
            value={fmt(totalValue)}
            sub={`${positions.length} position${positions.length !== 1 ? "s" : ""}`}
            positive={null}
          />
          {/* Net Deposits — editable */}
          <div className="rounded-xl px-5 py-4 flex flex-col gap-1.5"
            style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
            <div className="flex items-center justify-between">
              <span className="text-xs uppercase tracking-widest font-semibold" style={{ color: "var(--muted)" }}>
                Net Deposits
              </span>
              {!editingDeposits && (
                <button onClick={() => { setDepositsInput((netDeposits ?? 0).toFixed(2)); setEditingDeposits(true); }}
                  className="text-[11px] px-2 py-0.5 rounded transition-all hover:opacity-80"
                  style={{ color: "var(--muted2)", background: "var(--surface2)", border: "1px solid var(--border2)" }}>
                  edit
                </button>
              )}
            </div>
            {editingDeposits ? (
              <div className="flex items-center gap-2 mt-1">
                <span className="text-lg font-bold" style={{ color: "var(--muted2)" }}>£</span>
                <input
                  type="number" step="0.01" value={depositsInput}
                  onChange={e => setDepositsInput(e.target.value)}
                  onKeyDown={e => {
                    if (e.key === "Enter") { const v = parseFloat(depositsInput); if (!isNaN(v) && v > 0) { setNetDeposits(v); setEditingDeposits(false); } }
                    if (e.key === "Escape") setEditingDeposits(false);
                  }}
                  autoFocus
                  className="text-xl font-extrabold tabular-nums outline-none w-full rounded-lg px-2 py-1"
                  style={{ background: "var(--surface2)", border: "1px solid var(--border2)", color: "var(--text)" }}
                />
                <button onClick={() => { const v = parseFloat(depositsInput); if (!isNaN(v) && v > 0) { setNetDeposits(v); setEditingDeposits(false); } }}>
                  <Check size={15} style={{ color: "#22c55e" }} />
                </button>
                <button onClick={() => setEditingDeposits(false)}>
                  <X size={15} style={{ color: "var(--muted2)" }} />
                </button>
              </div>
            ) : (
              <div className="text-2xl font-extrabold tabular-nums" style={{ color: "var(--text)" }}>
                {netDeposits != null ? `£${netDeposits.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : "—"}
              </div>
            )}
            {!editingDeposits && (
              <div className="text-xs" style={{ color: "var(--muted)" }}>GBP deposited</div>
            )}
          </div>
          <SummaryCard
            label="Total P&L"
            value={`${totalPnl >= 0 ? "+" : ""}${fmt(totalPnl)}`}
            sub={`${totalPnlPct >= 0 ? "+" : ""}${totalPnlPct.toFixed(2)}% all time`}
            positive={totalPnl >= 0}
          />
          <SummaryCard
            label="Today's P&L"
            value={`${todayTotal >= 0 ? "+" : ""}${fmt(todayTotal)}`}
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
          <div className="flex gap-2">
            <button onClick={() => fileRef.current?.click()}
              className="flex items-center gap-1.5 text-xs px-4 py-2.5 rounded-xl font-semibold transition-all hover:opacity-85"
              style={{ background: "var(--surface2)", border: "1px solid var(--border2)", color: "var(--muted2)" }}>
              <Upload size={13} /> Import CSV
            </button>
            <button onClick={() => setShowForm(true)}
              className="flex items-center gap-1.5 text-xs px-4 py-2.5 rounded-xl font-semibold transition-all hover:opacity-85"
              style={{ background: "linear-gradient(135deg,#3b82f6,#6366f1)", color: "#fff" }}>
              <Plus size={13} /> Add manually
            </button>
          </div>
        </div>
      )}

      {/* ── Performance chart ── */}
      {positions.length > 0 && (
        <PortfolioPerformance positions={positions} transactions={transactions} netDeposits={netDeposits} usdToGbp={usdToGbp} />
      )}

      {/* ── Holdings table ── */}
      {rows.length > 0 && (
        <div className="rounded-xl overflow-hidden"
          style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>

          {/* Allocation bar + heatmap */}
          {totalValue > 0 && (
            <div className="px-5 pt-4 pb-4">

              {/* Bar */}
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
              <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2 mb-4">
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

              {/* Heatmap tiles */}
              <div className="text-xs font-semibold uppercase tracking-wider mb-2" style={{ color: "var(--muted)" }}>
                Today&apos;s Performance
              </div>
              <div className="flex flex-wrap gap-2">
                {rows
                  .filter(r => r.mktValue != null && r.mktValue > 0)
                  .sort((a, b) => (b.mktValue ?? 0) - (a.mktValue ?? 0))
                  .map(r => {
                    const weight   = (r.mktValue ?? 0) / totalValue;
                    const chg      = r.live?.changePct;
                    const isPos    = chg != null && chg > 0;
                    const isNeg    = chg != null && chg < 0;
                    const tileColor = isPos ? "#4ade80" : isNeg ? "#f87171" : "var(--muted)";
                    return (
                      <button key={r.ticker}
                        onClick={() => onSelectTicker(r.ticker)}
                        className="flex flex-col items-center justify-center rounded-xl transition-all hover:scale-[1.03] hover:brightness-110"
                        style={{
                          background:    heatmapBg(chg),
                          border:        `1px solid ${isPos ? "rgba(34,197,94,0.3)" : isNeg ? "rgba(220,38,38,0.3)" : "var(--border)"}`,
                          minWidth:      72,
                          flex:          `${Math.max(1, Math.round(weight * 100))}`,
                          height:        Math.max(72, Math.round(72 + weight * 80)),
                          padding:       "10px 8px",
                        }}>
                        <span className="text-sm font-extrabold leading-tight" style={{ color: "var(--text)" }}>
                          {r.ticker}
                        </span>
                        <span className="text-[11px] font-bold mt-1 tabular-nums" style={{ color: tileColor }}>
                          {chg != null ? `${chg >= 0 ? "+" : ""}${chg.toFixed(2)}%` : "—"}
                        </span>
                        <span className="text-[10px] mt-0.5 tabular-nums" style={{ color: "var(--muted)" }}>
                          {r.mktValue != null ? fmt(r.mktValue) : "—"}
                        </span>
                      </button>
                    );
                  })}
              </div>
            </div>
          )}

          {/* Sort controls */}
          <div className="px-5 py-3 flex items-center gap-2 border-t" style={{ borderColor: "var(--border)" }}>
            <span className="text-xs font-semibold uppercase tracking-wider mr-1" style={{ color: "var(--muted)" }}>Sort:</span>
            {([
              { key: "value",    label: "Position Size" },
              { key: "pnlPct",   label: "All-time P&L" },
              { key: "todayPct", label: "Today" },
            ] as const).map(({ key, label }) => {
              const active = sortBy === key;
              const arrow  = active ? (sortDir === "desc" ? " ↓" : " ↑") : "";
              return (
                <button key={key} onClick={() => toggleSort(key)}
                  className="text-xs px-3 py-1.5 rounded-lg font-semibold transition-all hover:opacity-85"
                  style={{
                    background: active ? "linear-gradient(135deg,#3b82f6,#6366f1)" : "var(--surface2)",
                    color:      active ? "#fff" : "var(--muted2)",
                    border:     active ? "none" : "1px solid var(--border2)",
                  }}>
                  {label}{arrow}
                </button>
              );
            })}
          </div>

          <div className="overflow-x-auto">
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
                {sortedRows.map((row, i) => (
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
                      {sym}{conv(row.avgCost).toFixed(2)}
                    </td>

                    {/* Current Price */}
                    <td className="px-4 py-3 tabular-nums font-semibold" style={{ color: "var(--text)" }}>
                      {row.live ? `${sym}${conv(row.live.price).toFixed(2)}` : (
                        <span style={{ color: "var(--muted)" }}>—</span>
                      )}
                    </td>

                    {/* Market Value */}
                    <td className="px-4 py-3 tabular-nums font-semibold" style={{ color: "var(--text)" }}>
                      {row.mktValue !== null ? fmt(row.mktValue) : "—"}
                    </td>

                    {/* P&L $ */}
                    <td className="px-4 py-3 tabular-nums font-semibold"
                      style={{ color: row.pnl !== null ? pctColor(row.pnl) : "var(--muted)" }}>
                      {row.pnl !== null
                        ? `${row.pnl >= 0 ? "+" : ""}${fmt(row.pnl)}`
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
                              ? `${row.todayPnl >= 0 ? "+" : ""}${fmt(row.todayPnl)}`
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
