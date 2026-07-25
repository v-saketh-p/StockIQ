"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { TrendingUp, Sun, Moon } from "lucide-react";
import { useTheme } from "./ThemeProvider";
import { API_BASE } from "@/lib/api";

export default function NavBar() {
  const { theme, toggle } = useTheme();
  const [online, setOnline] = useState<boolean | null>(null);

  useEffect(() => {
    async function ping() {
      try {
        const ctrl = new AbortController();
        const timer = setTimeout(() => ctrl.abort(), 3000);
        const res = await fetch(`${API_BASE}/api/market/indices`, { signal: ctrl.signal });
        clearTimeout(timer);
        setOnline(res.ok);
      } catch {
        setOnline(false);
      }
    }
    ping();
    const id = setInterval(ping, 30_000);
    return () => clearInterval(id);
  }, []);

  const dotColor =
    online === null  ? "var(--muted)"  :
    online           ? "#22c55e"       : "#ef4444";

  const dotTitle =
    online === null  ? "Checking backend…"                            :
    online           ? "Backend online"                               :
                       `Backend offline — start with: cd backend && uvicorn main:app --reload`;

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

      <div className="flex items-center gap-3">
        {/* Backend status dot */}
        <div
          title={dotTitle}
          className="flex items-center gap-1.5 text-[11px] px-2.5 py-1 rounded-full cursor-default select-none"
          style={{
            background: online === false ? "rgba(239,68,68,0.08)" : "transparent",
            border: online === false ? "1px solid rgba(239,68,68,0.2)" : "1px solid transparent",
          }}
        >
          <span
            className="w-1.5 h-1.5 rounded-full flex-shrink-0"
            style={{
              background: dotColor,
              boxShadow: online ? `0 0 5px ${dotColor}` : "none",
              transition: "background 0.3s, box-shadow 0.3s",
            }}
          />
          {online === false && (
            <span style={{ color: "#ef4444", fontWeight: 600 }}>Backend offline</span>
          )}
        </div>

        {/* Theme toggle */}
        <button
          onClick={toggle}
          title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          className="w-8 h-8 rounded-lg flex items-center justify-center transition-all hover:opacity-80"
          style={{
            background: "var(--surface2)",
            border: "1px solid var(--border)",
            color: "var(--muted2)",
          }}
        >
          {theme === "dark" ? <Sun size={14} /> : <Moon size={14} />}
        </button>
      </div>
    </nav>
  );
}
