"use client";

import Link from "next/link";
import { TrendingUp, Sun, Moon } from "lucide-react";
import { useTheme } from "./ThemeProvider";

export default function NavBar() {
  const { theme, toggle } = useTheme();

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
    </nav>
  );
}
