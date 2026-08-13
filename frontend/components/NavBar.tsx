"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { TrendingUp, Check, BarChart2, Briefcase, Zap, Menu, X,
         Palette, ChevronRight, Settings, Mail, Info, ExternalLink } from "lucide-react";
import { useTheme, THEMES, type Theme } from "./ThemeProvider";

const NAV_LINKS = [
  { href: "/research",  label: "Research",  icon: BarChart2 },
  { href: "/portfolio", label: "Portfolio", icon: Briefcase },
  { href: "/arm",       label: "ARM",       icon: Zap },
];

const sidePanelVariants = {
  hidden: { opacity: 0, x: 8, scale: 0.97 },
  show:   { opacity: 1, x: 0, scale: 1 },
  exit:   { opacity: 0, x: 8, scale: 0.97 },
};

export default function NavBar() {
  const { theme, setTheme } = useTheme();
  const [open, setOpen]           = useState(false);
  const [activePanel, setActivePanel] = useState<"theme" | "settings" | null>(null);
  const ref                       = useRef<HTMLDivElement>(null);
  const pathname                  = usePathname();

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
        setActivePanel(null);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  useEffect(() => { setOpen(false); setActivePanel(null); }, [pathname]);

  function togglePanel(panel: "theme" | "settings") {
    setActivePanel(p => p === panel ? null : panel);
  }

  function closeAll() { setOpen(false); setActivePanel(null); }

  const currentTheme = THEMES.find(t => t.id === theme);

  return (
    <nav className="flex items-center justify-between px-5 flex-shrink-0"
      style={{ height: 56, background: "var(--surface)", borderBottom: "1px solid var(--border)", zIndex: 50, position: "relative" }}>

      {/* Brand */}
      <Link href="/" className="flex items-center gap-2.5" style={{ textDecoration: "none" }}>
        <div className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0"
          style={{ background: "linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%)" }}>
          <TrendingUp size={14} color="#fff" strokeWidth={2.5} />
        </div>
        <span className="text-sm font-extrabold tracking-widest uppercase select-none"
          style={{ background: "linear-gradient(90deg, #3b82f6, #8b5cf6)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent", letterSpacing: "0.12em" }}>
          StockIQ
        </span>
      </Link>

      {/* Nav links — center */}
      <div className="flex items-center gap-1">
        {NAV_LINKS.map(({ href, label, icon: Icon }) => {
          const active = pathname === href;
          return (
            <Link key={href} href={href}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all hover:opacity-80"
              style={{
                background: active ? "var(--surface2)" : "transparent",
                color: active ? "var(--text)" : "var(--muted2)",
                border: active ? "1px solid var(--border)" : "1px solid transparent",
                textDecoration: "none",
              }}>
              <Icon size={12} />
              {label}
            </Link>
          );
        })}
      </div>

      {/* Hamburger — right */}
      <div ref={ref} style={{ position: "relative" }}>
        <button
          onClick={() => { setOpen(o => !o); setActivePanel(null); }}
          className="flex items-center justify-center w-9 h-9 rounded-lg"
          style={{ background: open ? "var(--surface2)" : "transparent", border: "1px solid var(--border)", color: "var(--muted2)", transition: "background 0.15s" }}
        >
          <AnimatePresence mode="wait" initial={false}>
            {open
              ? <motion.span key="x" initial={{ rotate: -90, opacity: 0 }} animate={{ rotate: 0, opacity: 1 }} exit={{ rotate: 90, opacity: 0 }} transition={{ duration: 0.15 }}>
                  <X size={16} />
                </motion.span>
              : <motion.span key="menu" initial={{ rotate: 90, opacity: 0 }} animate={{ rotate: 0, opacity: 1 }} exit={{ rotate: -90, opacity: 0 }} transition={{ duration: 0.15 }}>
                  <Menu size={16} />
                </motion.span>
            }
          </AnimatePresence>
        </button>

        {/* Main dropdown */}
        <AnimatePresence>
          {open && (
            <motion.div
              initial={{ opacity: 0, y: -8, scale: 0.97 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -8, scale: 0.97 }}
              transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
              className="absolute right-0 mt-2 rounded-2xl"
              style={{ width: 220, background: "var(--surface)", border: "1px solid var(--border2)", boxShadow: "0 16px 40px var(--shadow)", zIndex: 100, overflow: "visible" }}
            >
              <div className="p-2 flex flex-col gap-0.5">

                {/* ── Theme ── */}
                <div style={{ position: "relative" }}>
                  <button
                    onClick={() => togglePanel("theme")}
                    className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm hover:opacity-80"
                    style={{ background: activePanel === "theme" ? "var(--surface2)" : "transparent", color: "var(--text)", transition: "background 0.12s" }}
                  >
                    <Palette size={15} style={{ color: "var(--muted2)", flexShrink: 0 }} />
                    <span className="flex-1 text-left font-medium">Theme</span>
                    <div className="flex items-center gap-1.5">
                      {currentTheme && (
                        <div className="flex gap-1">
                          <div className="w-3 h-3 rounded-full border" style={{ background: currentTheme.bg, borderColor: "var(--border2)" }} />
                          <div className="w-3 h-3 rounded-full border" style={{ background: currentTheme.surface, borderColor: "var(--border2)" }} />
                        </div>
                      )}
                      <motion.span animate={{ rotate: activePanel === "theme" ? 90 : 0 }} transition={{ duration: 0.15 }}>
                        <ChevronRight size={13} style={{ color: "var(--muted2)" }} />
                      </motion.span>
                    </div>
                  </button>

                  <AnimatePresence>
                    {activePanel === "theme" && (
                      <motion.div
                        variants={sidePanelVariants} initial="hidden" animate="show" exit="exit"
                        transition={{ duration: 0.16, ease: [0.16, 1, 0.3, 1] }}
                        className="absolute rounded-2xl p-2"
                        style={{ right: "calc(100% + 8px)", top: 0, width: 190, background: "var(--surface)", border: "1px solid var(--border2)", boxShadow: "0 16px 40px var(--shadow)", zIndex: 101 }}
                      >
                        <div className="px-3 py-1.5 text-xs font-bold uppercase tracking-widest" style={{ color: "var(--muted)" }}>Theme</div>
                        {THEMES.map(t => (
                          <button key={t.id}
                            onClick={() => { setTheme(t.id as Theme); closeAll(); }}
                            className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm hover:opacity-80"
                            style={{ background: theme === t.id ? "var(--surface2)" : "transparent", color: "var(--text)", transition: "background 0.12s" }}>
                            <div className="flex gap-1 flex-shrink-0">
                              <div className="w-3.5 h-3.5 rounded-full border" style={{ background: t.bg, borderColor: "var(--border2)" }} />
                              <div className="w-3.5 h-3.5 rounded-full border" style={{ background: t.surface, borderColor: "var(--border2)" }} />
                            </div>
                            <span className="flex-1 text-left font-medium">{t.label}</span>
                            {theme === t.id && <Check size={13} style={{ color: "var(--blue)", flexShrink: 0 }} />}
                          </button>
                        ))}
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>

                {/* ── Settings ── */}
                <div style={{ position: "relative" }}>
                  <button
                    onClick={() => togglePanel("settings")}
                    className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm hover:opacity-80"
                    style={{ background: activePanel === "settings" ? "var(--surface2)" : "transparent", color: "var(--text)", transition: "background 0.12s" }}
                  >
                    <Settings size={15} style={{ color: "var(--muted2)", flexShrink: 0 }} />
                    <span className="flex-1 text-left font-medium">Settings</span>
                    <motion.span animate={{ rotate: activePanel === "settings" ? 90 : 0 }} transition={{ duration: 0.15 }}>
                      <ChevronRight size={13} style={{ color: "var(--muted2)" }} />
                    </motion.span>
                  </button>

                  <AnimatePresence>
                    {activePanel === "settings" && (
                      <motion.div
                        variants={sidePanelVariants} initial="hidden" animate="show" exit="exit"
                        transition={{ duration: 0.16, ease: [0.16, 1, 0.3, 1] }}
                        className="absolute rounded-2xl p-2"
                        style={{ right: "calc(100% + 8px)", top: 0, width: 190, background: "var(--surface)", border: "1px solid var(--border2)", boxShadow: "0 16px 40px var(--shadow)", zIndex: 101 }}
                      >
                        <div className="px-3 py-1.5 text-xs font-bold uppercase tracking-widest" style={{ color: "var(--muted)" }}>Settings</div>

                        <a href="mailto:vsaketh168@gmail.com"
                          className="flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm hover:opacity-80"
                          style={{ color: "var(--text)", textDecoration: "none", transition: "background 0.12s" }}
                          onClick={closeAll}>
                          <Mail size={14} style={{ color: "var(--muted2)", flexShrink: 0 }} />
                          <span className="font-medium">Send Feedback</span>
                        </a>

                        <a href="https://github.com/v-saketh-p/StockIQ" target="_blank" rel="noopener noreferrer"
                          className="flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm hover:opacity-80"
                          style={{ color: "var(--text)", textDecoration: "none", transition: "background 0.12s" }}
                          onClick={closeAll}>
                          <ExternalLink size={14} style={{ color: "var(--muted2)", flexShrink: 0 }} />
                          <span className="font-medium">GitHub</span>
                        </a>

                        <div style={{ height: 1, background: "var(--border)", margin: "4px 0" }} />

                        <div className="flex items-start gap-3 px-3 py-2.5 rounded-xl"
                          style={{ color: "var(--muted2)" }}>
                          <Info size={14} style={{ flexShrink: 0, marginTop: 2 }} />
                          <span className="text-xs leading-relaxed">StockIQ — institutional-grade research, free for everyone.</span>
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>

              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </nav>
  );
}
