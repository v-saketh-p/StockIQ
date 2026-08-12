"use client";

import Link from "next/link";
import { useState, useRef, useEffect } from "react";
import { TrendingUp, Palette, Check } from "lucide-react";
import { useTheme, THEMES, type Theme } from "./ThemeProvider";

export default function NavBar() {
  const { theme, setTheme } = useTheme();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  return (
    <nav
      className="flex items-center justify-between px-5 flex-shrink-0"
      style={{
        height: 56,
        background: "var(--surface)",
        borderBottom: "1px solid var(--border)",
        zIndex: 50,
      }}
    >
      {/* Brand */}
      <Link href="/" className="flex items-center gap-2.5" style={{ textDecoration: "none" }}>
        <div
          className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0"
          style={{ background: "linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%)" }}
        >
          <TrendingUp size={14} color="#fff" strokeWidth={2.5} />
        </div>
        <span
          className="text-sm font-extrabold tracking-widest uppercase select-none"
          style={{
            background: "linear-gradient(90deg, #3b82f6, #8b5cf6)",
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
            letterSpacing: "0.12em",
          }}
        >
          StockIQ
        </span>
      </Link>

      {/* Theme picker */}
      <div ref={ref} style={{ position: "relative" }}>
        <button
          onClick={() => setOpen(o => !o)}
          title="Change theme"
          className="flex items-center gap-2 px-3 h-8 rounded-lg text-xs font-semibold transition-all hover:opacity-80"
          style={{
            background: "var(--surface2)",
            border: "1px solid var(--border)",
            color: "var(--muted2)",
          }}
        >
          <Palette size={13} />
          <span>{THEMES.find(t => t.id === theme)?.label ?? "Theme"}</span>
        </button>

        {open && (
          <div
            className="absolute right-0 mt-2 rounded-xl overflow-hidden"
            style={{
              width: 180,
              background: "var(--surface)",
              border: "1px solid var(--border2)",
              boxShadow: "0 8px 24px var(--shadow)",
              zIndex: 100,
            }}
          >
            <div className="px-3 py-2 text-xs font-bold uppercase tracking-widest" style={{ color: "var(--muted)", borderBottom: "1px solid var(--border)" }}>
              Theme
            </div>
            {THEMES.map(t => (
              <button
                key={t.id}
                onClick={() => { setTheme(t.id as Theme); setOpen(false); }}
                className="w-full flex items-center gap-3 px-3 py-2.5 text-sm transition-all hover:opacity-80"
                style={{ background: theme === t.id ? "var(--surface2)" : "transparent", color: "var(--text)" }}
              >
                {/* Colour swatch */}
                <div className="flex gap-1 flex-shrink-0">
                  <div className="w-3.5 h-3.5 rounded-full border" style={{ background: t.bg, borderColor: "var(--border2)" }} />
                  <div className="w-3.5 h-3.5 rounded-full border" style={{ background: t.surface, borderColor: "var(--border2)" }} />
                </div>
                <span className="flex-1 text-left font-medium">{t.label}</span>
                {theme === t.id && <Check size={13} style={{ color: "var(--blue)", flexShrink: 0 }} />}
              </button>
            ))}
          </div>
        )}
      </div>
    </nav>
  );
}
