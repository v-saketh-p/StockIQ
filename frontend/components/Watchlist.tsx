"use client";

import { useState, useRef, useEffect } from "react";
import { X, Plus, ChevronRight, Pencil, Trash2 } from "lucide-react";

export interface WatchlistGroup {
  id: string;
  name: string;
  tickers: string[];
}

interface Props {
  watchlists: WatchlistGroup[];
  activeListId: string;
  activeTicker: string | null;
  onSelectTicker: (t: string) => void;
  onSelectList: (id: string) => void;
  onCreateList: (name: string) => void;
  onRenameList: (id: string, name: string) => void;
  onDeleteList: (id: string) => void;
  onRemoveTicker: (ticker: string, listId: string) => void;
}

export default function Watchlist({
  watchlists,
  activeListId,
  activeTicker,
  onSelectTicker,
  onSelectList,
  onCreateList,
  onRenameList,
  onDeleteList,
  onRemoveTicker,
}: Props) {
  const [creatingNew, setCreatingNew]   = useState(false);
  const [newName,     setNewName]       = useState("");
  const [editingId,   setEditingId]     = useState<string | null>(null);
  const [editName,    setEditName]      = useState("");
  const newInputRef  = useRef<HTMLInputElement>(null);
  const editInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => { if (creatingNew)  newInputRef.current?.focus();  }, [creatingNew]);
  useEffect(() => { if (editingId)    editInputRef.current?.focus(); }, [editingId]);

  function submitNew() {
    const name = newName.trim();
    if (name) onCreateList(name);
    setNewName("");
    setCreatingNew(false);
  }

  function submitEdit(id: string) {
    const name = editName.trim();
    if (name) onRenameList(id, name);
    setEditingId(null);
  }

  const activeList = watchlists.find(w => w.id === activeListId);

  return (
    <div className="flex flex-col gap-3 overflow-y-auto flex-1 min-h-0">

      {/* ── Watchlist group list ── */}
      <div className="flex flex-col gap-0.5">
        <div className="text-xs uppercase tracking-widest px-2 mb-1" style={{ color: "var(--muted)" }}>
          Watchlists
        </div>

        {watchlists.map(list => (
          <div key={list.id}>
            {editingId === list.id ? (
              <div className="px-2 py-0.5">
                <input
                  ref={editInputRef}
                  value={editName}
                  onChange={e => setEditName(e.target.value)}
                  onBlur={() => submitEdit(list.id)}
                  onKeyDown={e => {
                    if (e.key === "Enter")  submitEdit(list.id);
                    if (e.key === "Escape") setEditingId(null);
                  }}
                  className="w-full text-xs px-2 py-1.5 rounded-lg outline-none"
                  style={{
                    background: "var(--surface2)",
                    border: "1px solid var(--blue)",
                    color: "var(--text)",
                  }}
                />
              </div>
            ) : (
              <div
                className="flex items-center justify-between rounded-lg px-2 py-1.5 cursor-pointer group transition-colors"
                style={{
                  background: activeListId === list.id ? "rgba(59,130,246,0.1)" : "transparent",
                  border:     activeListId === list.id ? "1px solid rgba(59,130,246,0.2)" : "1px solid transparent",
                }}
                onClick={() => onSelectList(list.id)}
              >
                <div className="flex items-center gap-1.5 min-w-0">
                  <ChevronRight
                    size={10}
                    style={{
                      color: "var(--muted)",
                      transform: activeListId === list.id ? "rotate(90deg)" : "none",
                      transition: "transform 0.15s",
                      flexShrink: 0,
                    }}
                  />
                  <span
                    className="text-xs font-semibold truncate"
                    style={{ color: activeListId === list.id ? "var(--blue)" : "var(--text)" }}
                  >
                    {list.name}
                  </span>
                  <span className="text-xs flex-shrink-0" style={{ color: "var(--muted)", opacity: 0.6 }}>
                    {list.tickers.length}
                  </span>
                </div>

                {/* Hover actions */}
                <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0 ml-1">
                  <button
                    onClick={e => { e.stopPropagation(); setEditingId(list.id); setEditName(list.name); }}
                    className="p-0.5 rounded hover:opacity-70"
                    style={{ color: "var(--muted)" }}
                    title="Rename"
                  >
                    <Pencil size={10} />
                  </button>
                  {watchlists.length > 1 && (
                    <button
                      onClick={e => { e.stopPropagation(); onDeleteList(list.id); }}
                      className="p-0.5 rounded hover:opacity-70"
                      style={{ color: "var(--muted)" }}
                      title="Delete"
                    >
                      <Trash2 size={10} />
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>
        ))}

        {/* New watchlist input / button */}
        {creatingNew ? (
          <div className="px-2 py-0.5">
            <input
              ref={newInputRef}
              value={newName}
              onChange={e => setNewName(e.target.value)}
              onBlur={() => { if (!newName.trim()) setCreatingNew(false); else submitNew(); }}
              onKeyDown={e => {
                if (e.key === "Enter")  submitNew();
                if (e.key === "Escape") { setCreatingNew(false); setNewName(""); }
              }}
              placeholder="List name…"
              className="w-full text-xs px-2 py-1.5 rounded-lg outline-none"
              style={{
                background: "var(--surface2)",
                border: "1px solid var(--blue)",
                color: "var(--text)",
              }}
            />
          </div>
        ) : (
          <button
            onClick={() => setCreatingNew(true)}
            className="flex items-center gap-1.5 px-2 py-1.5 rounded-lg text-xs transition-opacity hover:opacity-70 mt-0.5"
            style={{ color: "var(--muted)" }}
          >
            <Plus size={11} />
            New watchlist
          </button>
        )}
      </div>

      {/* ── Tickers in active list ── */}
      {activeList && (
        <>
          <div style={{ height: 1, background: "var(--border)", flexShrink: 0 }} />
          <div className="flex flex-col gap-0.5">
            <div className="text-xs uppercase tracking-widest px-2 mb-1 truncate" style={{ color: "var(--muted)" }}>
              {activeList.name}
            </div>
            {activeList.tickers.length === 0 && (
              <div className="text-xs px-2 py-1" style={{ color: "var(--muted)" }}>
                No tickers yet
              </div>
            )}
            {activeList.tickers.map(t => (
              <div
                key={t}
                className="flex items-center justify-between rounded-lg px-3 py-2 cursor-pointer group transition-colors"
                style={{
                  background: activeTicker === t ? "var(--surface2)" : "transparent",
                  border:     activeTicker === t ? "1px solid var(--border)" : "1px solid transparent",
                }}
                onClick={() => onSelectTicker(t)}
              >
                <span
                  className="text-sm font-semibold"
                  style={{ color: activeTicker === t ? "var(--blue)" : "var(--text)" }}
                >
                  {t}
                </span>
                <button
                  onClick={e => { e.stopPropagation(); onRemoveTicker(t, activeListId); }}
                  className="opacity-0 group-hover:opacity-100 transition-opacity"
                  style={{ color: "var(--muted)" }}
                >
                  <X size={12} />
                </button>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
