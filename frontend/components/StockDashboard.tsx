"use client";

import { useEffect, useState } from "react";
import { TrendingUp, TrendingDown, Plus, RefreshCw, MessageSquare, X,
         DollarSign, BarChart2, Activity, Layers, Sparkles } from "lucide-react";
import PriceChart from "./PriceChart";
import MetricCard from "./MetricCard";
import TechnicalGauge from "./TechnicalGauge";
import AIReport from "./AIReport";
import ChatPanel from "./ChatPanel";

interface StockData {
  ticker: string;
  name: string;
  sector: string;
  industry: string;
  price: number;
  change: number;
  preMarket:  { price: number | null; changePct: number | null };
  postMarket: { price: number | null; changePct: number | null };
  marketCap: number | null;
  valuation: { peTrailing: number | null; peForward: number | null; evEbitda: number | null };
  profitability: {
    roe: number | null; grossMargin: number | null; operatingMargin: number | null;
    netMargin: number | null; revenueGrowth: number | null; epsGrowth: number | null;
  };
  balanceSheet: { debtEquity: number | null; freeCashFlow: number | null };
  technicals: {
    rsi: number | null; macd: number | null; macdSignal: number | null;
    vwap: number | null; ma50: number; ma200: number; volume: number; volumeAvg20: number;
  };
  chart: { date: string; close: number; volume: number }[];
}

function fmt(v: number | null, decimals = 2, suffix = "") {
  if (v === null || v === undefined) return "N/A";
  return v.toFixed(decimals) + suffix;
}

function fmtBig(v: number | null) {
  if (v === null) return "N/A";
  if (v >= 1e12) return `$${(v / 1e12).toFixed(2)}T`;
  if (v >= 1e9)  return `$${(v / 1e9).toFixed(2)}B`;
  if (v >= 1e6)  return `$${(v / 1e6).toFixed(2)}M`;
  return `$${v}`;
}

function QuickStat({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="rounded-xl px-4 py-3 flex flex-col gap-1"
      style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
      <div className="text-xs" style={{ color: "var(--muted)" }}>{label}</div>
      <div className="text-lg font-bold tabular-nums" style={{ color }}>{value}</div>
    </div>
  );
}

function MetricPanel({
  title, color, icon, children,
}: {
  title: string; color: string; icon: React.ReactNode; children: React.ReactNode;
}) {
  return (
    <div className="rounded-xl p-4 flex flex-col gap-3"
      style={{ background: "var(--surface)", border: "1px solid var(--border)", borderTop: `2px solid ${color}` }}>
      <div className="flex items-center gap-2">
        <div className="w-6 h-6 rounded-md flex items-center justify-center flex-shrink-0"
          style={{ background: `${color}1a` }}>
          <span style={{ color }}>{icon}</span>
        </div>
        <span className="text-xs font-bold uppercase tracking-widest" style={{ color: "var(--muted2)" }}>
          {title}
        </span>
      </div>
      <div className="flex flex-col gap-2.5">{children}</div>
    </div>
  );
}

export default function StockDashboard({
  ticker,
  onAddToWatchlist,
}: {
  ticker: string;
  onAddToWatchlist: (t: string) => void;
}) {
  const [data,      setData]      = useState<StockData | null>(null);
  const [loading,   setLoading]   = useState(false);
  const [error,     setError]     = useState<string | null>(null);
  const [chatOpen,  setChatOpen]  = useState(false);
  const [activeTab, setActiveTab] = useState<"overview" | "research">("overview");

  async function fetchData() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`http://localhost:8000/api/stock/${ticker}`);
      if (!res.ok) { const j = await res.json(); throw new Error(j.detail || "Failed to fetch"); }
      setData(await res.json());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { fetchData(); }, [ticker]);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-3">
        <RefreshCw size={20} className="animate-spin" style={{ color: "var(--blue)" }} />
        <span className="text-sm" style={{ color: "var(--muted2)" }}>Loading {ticker}…</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-3">
        <div className="text-sm font-semibold" style={{ color: "var(--red)" }}>Could not load {ticker}</div>
        <div className="text-xs" style={{ color: "var(--muted)" }}>{error}</div>
        <button onClick={fetchData}
          className="text-xs px-3 py-1.5 rounded-lg font-semibold hover:opacity-80 transition-opacity"
          style={{ background: "rgba(59,130,246,0.15)", color: "var(--blue)" }}>
          Try again
        </button>
      </div>
    );
  }

  if (!data) return null;

  const { technicals: tech, profitability: prof, valuation: val, balanceSheet: bs } = data;
  const up        = data.change >= 0;
  const pre       = data.preMarket?.changePct;
  const post      = data.postMarket?.changePct;
  const volRatio  = tech.volumeAvg20 ? tech.volume / tech.volumeAvg20 : null;
  const macdBull  = tech.macd !== null && tech.macdSignal !== null && tech.macd > tech.macdSignal;

  return (
    <>
    <div className="flex flex-col gap-5">

      {/* ── Hero ── */}
      <div className="rounded-2xl overflow-hidden"
        style={{ background: "var(--surface)", border: "1px solid var(--border2)", boxShadow: "0 1px 4px var(--shadow)" }}>
        {/* Rainbow accent bar */}
        <div className="h-0.5" style={{ background: "linear-gradient(90deg, #3b82f6 0%, #8b5cf6 50%, #ec4899 100%)" }} />

        <div className="px-6 py-5 flex items-start justify-between gap-4">
          {/* Left: identity */}
          <div className="flex flex-col gap-1.5 min-w-0">
            <div className="flex items-center gap-3 flex-wrap">
              <h1 className="text-4xl font-extrabold tracking-tight" style={{ color: "var(--text)" }}>
                {data.ticker}
              </h1>

              {/* Day change */}
              <span className="flex items-center gap-1.5 text-sm font-bold px-3 py-1.5 rounded-lg"
                style={{
                  background: up ? "rgba(34,197,94,0.12)" : "rgba(239,68,68,0.12)",
                  color: up ? "var(--green)" : "var(--red)",
                  border: `1px solid ${up ? "rgba(34,197,94,0.2)" : "rgba(239,68,68,0.2)"}`,
                }}>
                {up ? <TrendingUp size={13} /> : <TrendingDown size={13} />}
                {up ? "+" : ""}{fmt(data.change)}%
                <span className="font-normal text-xs" style={{ opacity: 0.6 }}>1D</span>
              </span>

              {/* Pre-market */}
              {pre !== null && pre !== undefined && (
                <span className="flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-lg"
                  style={{ background: "rgba(107,114,128,0.08)", color: pre >= 0 ? "var(--green)" : "var(--red)", border: "1px solid rgba(107,114,128,0.15)" }}>
                  {pre >= 0 ? "+" : ""}{pre.toFixed(2)}%
                  <span style={{ color: "var(--muted)", fontWeight: 400 }}>PRE</span>
                </span>
              )}

              {/* After-hours */}
              {post !== null && post !== undefined && (
                <span className="flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-lg"
                  style={{ background: "rgba(245,158,11,0.08)", color: post >= 0 ? "var(--green)" : "var(--red)", border: "1px solid rgba(245,158,11,0.15)" }}>
                  {post >= 0 ? "+" : ""}{post.toFixed(2)}%
                  <span style={{ color: "#f59e0b", fontWeight: 400 }}>AH</span>
                </span>
              )}
            </div>

            {/* Company name + sector + industry */}
            <div className="flex items-center gap-2 flex-wrap mt-0.5">
              <span className="text-sm font-medium" style={{ color: "var(--muted2)" }}>{data.name}</span>
              {data.sector && (
                <>
                  <span style={{ color: "var(--border2)" }}>·</span>
                  <span className="text-xs px-2 py-0.5 rounded-md font-medium"
                    style={{ background: "rgba(139,92,246,0.1)", color: "var(--purple)", border: "1px solid rgba(139,92,246,0.18)" }}>
                    {data.sector}
                  </span>
                </>
              )}
              {data.industry && (
                <span className="text-xs" style={{ color: "var(--muted)" }}>{data.industry}</span>
              )}
            </div>

            <div className="text-xs mt-0.5" style={{ color: "var(--muted)" }}>
              {fmtBig(data.marketCap)} market cap
            </div>
          </div>

          {/* Right: price + actions */}
          <div className="flex flex-col items-end gap-3 flex-shrink-0">
            <div>
              <div className="text-4xl font-extrabold tabular-nums text-right" style={{ color: "var(--text)" }}>
                ${fmt(data.price)}
              </div>
              {data.preMarket?.price && (
                <div className="text-xs text-right mt-0.5" style={{ color: "var(--muted)" }}>
                  Pre: ${data.preMarket.price.toFixed(2)}
                </div>
              )}
            </div>
            <div className="flex gap-2">
              <button onClick={() => onAddToWatchlist(data.ticker)}
                className="flex items-center gap-1.5 text-xs px-3 py-2 rounded-lg font-semibold transition-all hover:opacity-80"
                style={{ background: "var(--surface2)", border: "1px solid var(--border2)", color: "var(--muted2)" }}>
                <Plus size={12} /> Watchlist
              </button>
              <button onClick={fetchData} title="Refresh"
                className="w-8 h-8 flex items-center justify-center rounded-lg transition-all hover:opacity-80"
                style={{ background: "var(--surface2)", border: "1px solid var(--border2)", color: "var(--muted2)" }}>
                <RefreshCw size={13} />
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* ── Quick stats strip ── */}
      <div className="grid grid-cols-4 gap-3">
        <QuickStat label="P/E (Forward)"  value={val.peForward  !== null ? `${fmt(val.peForward, 1)}x`  : "N/A"} color="#f59e0b" />
        <QuickStat label="Gross Margin"   value={prof.grossMargin !== null ? `${fmt(prof.grossMargin, 1)}%`  : "N/A"} color="#22c55e" />
        <QuickStat label="RSI 14"         value={tech.rsi !== null ? fmt(tech.rsi, 1) : "N/A"} color="#06b6d4" />
        <QuickStat label="Vol / 20d Avg"  value={volRatio !== null ? `${volRatio.toFixed(2)}x` : "N/A"} color="#8b5cf6" />
      </div>

      {/* ── Chart ── */}
      <div className="rounded-xl overflow-hidden" style={{ border: "1px solid var(--border)" }}>
        <PriceChart ticker={data.ticker} ma50={tech.ma50} ma200={tech.ma200} />
      </div>

      {/* ── Tab bar ── */}
      <div className="flex gap-1 p-1 rounded-xl"
        style={{ background: "var(--surface2)", border: "1px solid var(--border)" }}>
        {([
          { id: "overview",  label: "Overview",    icon: <BarChart2 size={12} /> },
          { id: "research",  label: "AI Research", icon: <Sparkles  size={12} /> },
        ] as const).map(tab => (
          <button key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className="flex-1 flex items-center justify-center gap-1.5 text-xs font-semibold py-2 rounded-lg transition-all"
            style={activeTab === tab.id
              ? { background: "var(--surface)", color: "var(--text)", boxShadow: "0 1px 3px var(--shadow)" }
              : { color: "var(--muted2)" }
            }>
            {tab.icon}
            {tab.label}
          </button>
        ))}
      </div>

      {/* ── Tab content ── */}

      {/* Overview metrics — only render when active */}
      {activeTab === "overview" && (
        <div className="grid grid-cols-2 gap-4">

          {/* Valuation */}
          <MetricPanel title="Valuation" color="#f59e0b" icon={<DollarSign size={12} />}>
            <MetricCard label="P/E (trailing)" value={fmt(val.peTrailing)} />
            <MetricCard label="P/E (forward)"  value={fmt(val.peForward)} />
            <MetricCard label="EV / EBITDA"    value={fmt(val.evEbitda)} />
          </MetricPanel>

          {/* Profitability */}
          <MetricPanel title="Profitability" color="#22c55e" icon={<BarChart2 size={12} />}>
            <MetricCard label="Gross Margin"     value={fmt(prof.grossMargin, 2, "%")}     positive={prof.grossMargin     !== null ? prof.grossMargin > 0     : null} />
            <MetricCard label="Operating Margin" value={fmt(prof.operatingMargin, 2, "%")} positive={prof.operatingMargin !== null ? prof.operatingMargin > 0 : null} />
            <MetricCard label="Net Margin"       value={fmt(prof.netMargin, 2, "%")}       positive={prof.netMargin       !== null ? prof.netMargin > 0       : null} />
            <MetricCard label="ROE"              value={fmt(prof.roe, 2, "%")}             positive={prof.roe             !== null ? prof.roe > 0             : null} />
            <MetricCard label="Revenue Growth"   value={fmt(prof.revenueGrowth, 2, "%")}  positive={prof.revenueGrowth   !== null ? prof.revenueGrowth > 0   : null} />
            <MetricCard label="EPS Growth"       value={fmt(prof.epsGrowth, 2, "%")}      positive={prof.epsGrowth       !== null ? prof.epsGrowth > 0       : null} />
          </MetricPanel>

          {/* Balance Sheet */}
          <MetricPanel title="Balance Sheet" color="#3b82f6" icon={<Layers size={12} />}>
            <MetricCard label="Debt / Equity"  value={fmt(bs.debtEquity)}
              positive={bs.debtEquity !== null ? bs.debtEquity < 50 : null} />
            <MetricCard label="Free Cash Flow"
              value={bs.freeCashFlow !== null ? `$${(bs.freeCashFlow / 1e9).toFixed(2)}B` : "N/A"}
              positive={bs.freeCashFlow !== null ? bs.freeCashFlow > 0 : null} />
          </MetricPanel>

          {/* Technicals */}
          <MetricPanel title="Technicals" color="#06b6d4" icon={<Activity size={12} />}>
            <TechnicalGauge label="RSI (14)" value={tech.rsi} min={0} max={100} low={30} high={70} />
            <MetricCard label="MACD"      value={fmt(tech.macd)}  positive={macdBull} note={macdBull ? "Bullish ↑" : "Bearish ↓"} />
            <MetricCard label="VWAP"      value={tech.vwap !== null ? `$${fmt(tech.vwap)}` : "N/A"}
              positive={tech.vwap !== null ? data.price > tech.vwap : null}
              note={tech.vwap !== null ? (data.price > tech.vwap ? "↑ above" : "↓ below") : ""} />
            <MetricCard label="50-Day MA"  value={`$${fmt(tech.ma50)}`}  positive={data.price > tech.ma50}  note={data.price > tech.ma50  ? "↑ above" : "↓ below"} />
            <MetricCard label="200-Day MA" value={`$${fmt(tech.ma200)}`} positive={data.price > tech.ma200} note={data.price > tech.ma200 ? "↑ above" : "↓ below"} />
          </MetricPanel>

        </div>
      )}

      {/* AI Report — always mounted so report state persists across tab switches; hidden when not active */}
      <div style={{ display: activeTab === "research" ? "block" : "none" }}>
        <AIReport ticker={data.ticker} autoTrigger={activeTab === "research"} />
      </div>

    </div>

    {chatOpen && (
      <ChatPanel ticker={data.ticker} companyName={data.name} onClose={() => setChatOpen(false)} />
    )}

    {/* Floating chat button */}
    <button
      onClick={() => setChatOpen(o => !o)}
      title={chatOpen ? "Close chat" : `Chat about ${data.ticker}`}
      style={{
        position: "fixed", bottom: 28, right: 28, zIndex: 60,
        width: 56, height: 56, borderRadius: "50%",
        background: chatOpen ? "var(--surface2)" : "linear-gradient(135deg,#3b82f6,#6366f1)",
        border: chatOpen ? "1px solid var(--border)" : "none",
        boxShadow: chatOpen ? "0 4px 20px rgba(0,0,0,0.4)" : "0 4px 28px rgba(59,130,246,0.45)",
        display: "flex", alignItems: "center", justifyContent: "center",
        cursor: "pointer", transition: "all 0.2s ease", color: "#fff",
      }}
    >
      {chatOpen ? <X size={20} style={{ color: "var(--muted2)" }} /> : <MessageSquare size={22} />}
    </button>
    </>
  );
}
