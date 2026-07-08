"use client";

import { useState, useEffect } from "react";
import SearchBar from "@/components/SearchBar";
import StockDashboard from "@/components/StockDashboard";
import Watchlist, { WatchlistGroup } from "@/components/Watchlist";
import PortfolioTracker from "@/components/PortfolioTracker";
import ARMSignals from "@/components/ARMSignals";
import { BarChart2, Briefcase, Zap } from "lucide-react";

function genId() {
  return Math.random().toString(36).slice(2, 9);
}

const DEFAULT_WATCHLISTS: WatchlistGroup[] = [
  { id: "default", name: "My Watchlist", tickers: ["AAPL", "GOOG", "NVDA"] },
];

export default function Home() {
  const [ticker,       setTicker]       = useState<string | null>(null);
  const [watchlists,   setWatchlists]   = useState<WatchlistGroup[]>(DEFAULT_WATCHLISTS);
  const [activeListId, setActiveListId] = useState<string>("default");
  const [view,         setView]         = useState<"research" | "portfolio" | "arm">("research");

  // Load from localStorage after mount
  useEffect(() => {
    try {
      const saved = localStorage.getItem("watchlists");
      if (saved) setWatchlists(JSON.parse(saved));
      const savedId = localStorage.getItem("activeListId");
      if (savedId) setActiveListId(savedId);
    } catch {}
  }, []);

  // Persist on change
  useEffect(() => {
    localStorage.setItem("watchlists", JSON.stringify(watchlists));
  }, [watchlists]);

  useEffect(() => {
    localStorage.setItem("activeListId", activeListId);
  }, [activeListId]);

  // Resolve activeListId in case a list was deleted
  const activeListExists = watchlists.some(w => w.id === activeListId);
  const resolvedId = activeListExists ? activeListId : (watchlists[0]?.id ?? "");

  function addToWatchlist(t: string) {
    setWatchlists(prev => prev.map(list =>
      list.id === resolvedId && !list.tickers.includes(t)
        ? { ...list, tickers: [...list.tickers, t] }
        : list
    ));
  }

  function removeFromWatchlist(t: string, listId: string) {
    setWatchlists(prev => prev.map(list =>
      list.id === listId
        ? { ...list, tickers: list.tickers.filter(x => x !== t) }
        : list
    ));
  }

  function createWatchlist(name: string) {
    const id = genId();
    setWatchlists(prev => [...prev, { id, name, tickers: [] }]);
    setActiveListId(id);
  }

  function renameWatchlist(id: string, name: string) {
    setWatchlists(prev => prev.map(list =>
      list.id === id ? { ...list, name } : list
    ));
  }

  function deleteWatchlist(id: string) {
    setWatchlists(prev => {
      const next = prev.filter(list => list.id !== id);
      if (activeListId === id) setActiveListId(next[0]?.id ?? "");
      return next;
    });
  }

  const QUICK_PICKS = ["AAPL", "NVDA", "TSLA", "AMZN", "META", "GOOG"];

  return (
    <div className="flex overflow-hidden" style={{ height: "calc(100vh - 56px)", background: "var(--background)" }}>
      {/* Sidebar */}
      <aside
        className="w-56 flex-shrink-0 flex flex-col border-r py-4 px-3 gap-3 overflow-hidden"
        style={{ background: "var(--surface)", borderColor: "var(--border)" }}
      >
        {/* View toggle */}
        <div className="flex gap-1 p-1 rounded-xl flex-shrink-0"
          style={{ background: "var(--surface2)", border: "1px solid var(--border)" }}>
          {([
            { id: "research",  label: "Research",  icon: <BarChart2 size={11} /> },
            { id: "portfolio", label: "Portfolio", icon: <Briefcase size={11} /> },
            { id: "arm",       label: "ARM",       icon: <Zap size={11} /> },
          ] as const).map(v => (
            <button key={v.id} onClick={() => setView(v.id)}
              className="flex-1 flex items-center justify-center gap-1 text-[11px] font-semibold py-1.5 rounded-lg transition-all"
              style={view === v.id
                ? { background: "var(--surface)", color: "var(--text)", boxShadow: "0 1px 3px var(--shadow)" }
                : { color: "var(--muted2)" }}>
              {v.icon}{v.label}
            </button>
          ))}
        </div>

        {view === "research" && (
          <Watchlist
            watchlists={watchlists}
            activeListId={resolvedId}
            activeTicker={ticker}
            onSelectTicker={setTicker}
            onSelectList={setActiveListId}
            onCreateList={createWatchlist}
            onRenameList={renameWatchlist}
            onDeleteList={deleteWatchlist}
            onRemoveTicker={removeFromWatchlist}
          />
        )}
      </aside>

      {/* Main */}
      <main className="flex-1 flex flex-col overflow-hidden">
        {/* Search header */}
        <header
          className="flex items-center gap-4 px-6 py-3.5 border-b flex-shrink-0"
          style={{ background: "var(--surface)", borderColor: "var(--border)" }}
        >
          <SearchBar
            onSearch={t => {
              setTicker(t);
              addToWatchlist(t);
            }}
          />
        </header>

        <div className="flex-1 overflow-y-auto p-6" data-scroll>
          {view === "arm" ? (
            <ARMSignals onSelectTicker={t => { setTicker(t); setView("research"); }} />
          ) : view === "portfolio" ? (
            <PortfolioTracker onSelectTicker={t => { setTicker(t); setView("research"); }} />
          ) : ticker ? (
            <StockDashboard ticker={ticker} onAddToWatchlist={addToWatchlist} />
          ) : (
            <div className="flex flex-col items-center justify-center h-full gap-6">
              {/* Icon */}
              <div className="w-20 h-20 rounded-3xl flex items-center justify-center"
                style={{ background: "linear-gradient(135deg,rgba(59,130,246,0.15),rgba(139,92,246,0.15))", border: "1px solid rgba(59,130,246,0.2)" }}>
                <span className="text-4xl select-none">📈</span>
              </div>
              <div className="text-center flex flex-col gap-1.5">
                <div className="text-xl font-bold" style={{ color: "var(--text)" }}>
                  Research any stock
                </div>
                <div className="text-sm" style={{ color: "var(--muted2)" }}>
                  Search a ticker above for price, fundamentals, technicals, and AI analysis
                </div>
              </div>
              {/* Quick picks */}
              <div className="flex flex-col items-center gap-2">
                <div className="text-xs uppercase tracking-widest" style={{ color: "var(--muted)" }}>Quick picks</div>
                <div className="flex gap-2 flex-wrap justify-center">
                  {QUICK_PICKS.map(t => (
                    <button key={t}
                      onClick={() => { setTicker(t); addToWatchlist(t); }}
                      className="px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all hover:opacity-80"
                      style={{ background: "var(--surface2)", border: "1px solid var(--border2)", color: "var(--text)" }}>
                      {t}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
