"use client";

import { useState, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { motion } from "framer-motion";
import { TrendingUp, Search, BarChart2, Briefcase, Zap, Sparkles,
         ArrowRight, ChevronRight } from "lucide-react";

const SUGGESTIONS = ["AAPL", "NVDA", "TSLA", "AMZN", "META", "GOOG", "MSFT", "AMD"];

const FEATURES = [
  {
    icon: BarChart2,
    title: "Deep Stock Research",
    desc: "Price, fundamentals, technicals, valuation, and comps — everything in one place. Powered by live market data.",
    color: "#3b82f6",
    href: "/research",
  },
  {
    icon: Sparkles,
    title: "AI-Powered Analysis",
    desc: "Claude AI reads filings, news, and earnings to generate institutional-quality research reports in seconds.",
    color: "#8b5cf6",
    href: "/research",
  },
  {
    icon: Zap,
    title: "ARM Strategy",
    desc: "Adaptive Regime Momentum — a quantitative signal scanner across 113 stocks with bi-weekly rebalancing.",
    color: "#10b981",
    href: "/arm",
  },
  {
    icon: Briefcase,
    title: "Portfolio Tracker",
    desc: "Track your holdings, monitor live P&L, and analyse performance across currencies and sectors.",
    color: "#f59e0b",
    href: "/portfolio",
  },
];

const fade = { hidden: { opacity: 0, y: 24 }, show: { opacity: 1, y: 0, transition: { duration: 0.6, ease: [0.16,1,0.3,1] as [number,number,number,number] } } };
const stagger = { hidden: {}, show: { transition: { staggerChildren: 0.1 } } };

export default function LandingPage() {
  const router      = useRouter();
  const [query, setQuery] = useState("");
  const [focused, setFocused] = useState(false);
  const inputRef    = useRef<HTMLInputElement>(null);

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    const t = query.trim().toUpperCase();
    if (t) router.push(`/research?ticker=${t}`);
  }

  return (
    <div className="flex flex-col min-h-full" style={{ background: "var(--background)", position: "relative" }}>

      {/* Full-page video background */}
      <video
        autoPlay
        loop
        muted
        playsInline
        style={{
          position: "fixed",
          inset: 0,
          width: "100%",
          height: "100%",
          objectFit: "cover",
          zIndex: 0,
          pointerEvents: "none",
          opacity: 0.45,
        }}
      >
        <source src="/background.mp4" type="video/mp4" />
      </video>

      {/* ── Minimal landing navbar ── */}
      <nav className="flex items-center justify-between px-8 flex-shrink-0"
        style={{ height: 60, background: "transparent", position: "relative", zIndex: 1 }}>
        <Link href="/" className="flex items-center gap-2.5" style={{ textDecoration: "none" }}>
          <div className="w-7 h-7 rounded-lg flex items-center justify-center"
            style={{ background: "linear-gradient(135deg,#3b82f6,#8b5cf6)" }}>
            <TrendingUp size={14} color="#fff" strokeWidth={2.5} />
          </div>
          <span className="text-sm font-extrabold tracking-widest uppercase"
            style={{ background: "linear-gradient(90deg,#3b82f6,#8b5cf6)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
            StockIQ
          </span>
        </Link>

        <Link href="/research"
          className="flex items-center gap-2 text-xs font-semibold px-4 py-2 rounded-lg transition-all hover:opacity-80"
          style={{ background: "var(--surface2)", border: "1px solid var(--border)", color: "var(--text)", textDecoration: "none" }}>
          Launch App <ArrowRight size={12} />
        </Link>
      </nav>

      {/* ── Hero ── */}
      <section className="flex flex-col items-center justify-center text-center px-6 py-24 gap-8 relative" style={{ zIndex: 1 }}>

        <motion.div variants={stagger} initial="hidden" animate="show"
          className="flex flex-col items-center gap-8 relative" style={{ zIndex: 1 }}>

          {/* Headline */}
          <motion.div variants={fade} className="flex flex-col gap-3">
            <h1 className="font-extrabold leading-tight"
              style={{ fontSize: "clamp(2.5rem, 6vw, 4.5rem)", color: "var(--text)", letterSpacing: "-0.03em" }}>
              Research smarter.
            </h1>
            <h1 className="font-extrabold leading-tight"
              style={{ fontSize: "clamp(2.5rem, 6vw, 4.5rem)", letterSpacing: "-0.03em",
                background: "linear-gradient(90deg,#3b82f6 0%,#8b5cf6 50%,#06b6d4 100%)",
                WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
              Invest better.
            </h1>
          </motion.div>

          <motion.p variants={fade} className="text-base max-w-xl leading-relaxed"
            style={{ color: "var(--muted2)" }}>
            Institutional-grade stock research — fundamentals, technicals, AI reports, and quantitative signals — free, for everyone.
          </motion.p>

          {/* Search box */}
          <motion.form variants={fade} onSubmit={handleSearch}
            className="w-full max-w-md flex gap-2">
            <div className="flex-1 flex items-center gap-2 rounded-xl px-4 py-3"
              style={{
                background: "var(--surface)",
                border: `1px solid ${focused ? "var(--blue)" : "var(--border2)"}`,
                boxShadow: focused ? "0 0 0 3px rgba(59,130,246,0.15)" : "none",
                transition: "border-color 0.15s ease, box-shadow 0.15s ease",
              }}>
              <Search size={15} style={{ color: "var(--muted)", flexShrink: 0 }} />
              <input
                ref={inputRef}
                value={query}
                onChange={e => setQuery(e.target.value.toUpperCase())}
                onFocus={() => setFocused(true)}
                onBlur={() => setFocused(false)}
                placeholder="Enter a ticker — e.g. AAPL, TSLA"
                className="flex-1 bg-transparent outline-none text-sm font-medium tabular-nums"
                style={{ color: "var(--text)" }}
                autoComplete="off"
                spellCheck={false}
              />
            </div>
            <button type="submit"
              className="flex items-center gap-1.5 px-5 py-3 rounded-xl text-sm font-bold"
              style={{ background: "linear-gradient(135deg,#3b82f6,#6366f1)", color: "#fff", flexShrink: 0 }}>
              Search <ChevronRight size={14} />
            </button>
          </motion.form>

        </motion.div>
      </section>

      {/* ── Features ── */}
      <section className="px-6 pb-24" style={{ position: "relative", zIndex: 1 }}>
        <div className="max-w-5xl mx-auto">
          <motion.div variants={stagger} initial="hidden" whileInView="show" viewport={{ once: true, amount: 0.2 }}
            className="grid grid-cols-2 gap-4" style={{ gridTemplateColumns: "repeat(2, 1fr)" }}>
            {FEATURES.map(({ icon: Icon, title, desc, color, href }) => (
              <motion.div key={title} variants={fade}>
                <Link href={href} style={{ textDecoration: "none" }}>
                  <motion.div
                    whileHover={{ y: -4, boxShadow: `0 16px 40px rgba(0,0,0,0.4), 0 0 0 1px ${color}44` }}
                    transition={{ type: "spring", stiffness: 260, damping: 22 }}
                    className="rounded-2xl p-6 h-full flex flex-col gap-4"
                    style={{
                      background: "rgba(255,255,255,0.04)",
                      backdropFilter: "blur(20px)",
                      WebkitBackdropFilter: "blur(20px)",
                      border: "1px solid rgba(255,255,255,0.08)",
                      borderTop: `2px solid ${color}`,
                      cursor: "pointer",
                    }}>
                    <div className="w-10 h-10 rounded-xl flex items-center justify-center"
                      style={{ background: `${color}20` }}>
                      <Icon size={20} style={{ color }} />
                    </div>
                    <div className="flex flex-col gap-1.5">
                      <h3 className="text-base font-bold" style={{ color: "var(--text)" }}>{title}</h3>
                      <p className="text-sm leading-relaxed" style={{ color: "var(--muted2)" }}>{desc}</p>
                    </div>
                    <div className="flex items-center gap-1 text-xs font-semibold mt-auto" style={{ color }}>
                      Explore <ChevronRight size={12} />
                    </div>
                  </motion.div>
                </Link>
              </motion.div>
            ))}
          </motion.div>
        </div>
      </section>

      {/* ── Footer ── */}
      <footer className="mt-auto px-8 py-6 flex items-center justify-between border-t"
        style={{ position: "relative", zIndex: 1, borderColor: "var(--border)", color: "var(--muted)" }}>
        <span className="text-xs">© 2026 StockIQ</span>
        <div className="flex items-center gap-4">
          <Link href="/research" className="text-xs hover:opacity-80" style={{ color: "var(--muted)", textDecoration: "none" }}>Research</Link>
          <Link href="/portfolio" className="text-xs hover:opacity-80" style={{ color: "var(--muted)", textDecoration: "none" }}>Portfolio</Link>
          <Link href="/arm" className="text-xs hover:opacity-80" style={{ color: "var(--muted)", textDecoration: "none" }}>ARM</Link>
        </div>
      </footer>
    </div>
  );
}
