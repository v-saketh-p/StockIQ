"use client";

import { useState, useRef, useEffect } from "react";
import { Sparkles, RefreshCw, TrendingUp, TrendingDown, Minus, RotateCcw } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface Props { ticker: string; autoTrigger?: boolean }

const PLUGINS = {
  "equity-research":    { color: "#8b5cf6", label: "Equity Research"    },
  "financial-analysis": { color: "#f59e0b", label: "Financial Analysis" },
  "earnings-reviewer":  { color: "#3b82f6", label: "Earnings Reviewer"  },
  "market-researcher":  { color: "#22c55e", label: "Market Research"    },
} as const;
type Plugin = keyof typeof PLUGINS;

function getPlugin(heading: string): Plugin {
  const h = heading.toLowerCase();
  if (h.includes("dcf") || h.includes("comparable") || h.includes("comps") || h.includes("profitability") || h.includes("3-statement")) return "financial-analysis";
  if (h.includes("earnings") || h.includes("estimates") || h.includes("quality")) return "earnings-reviewer";
  if (h.includes("business overview") || h.includes("sector") || h.includes("competitive")) return "market-researcher";
  return "equity-research";
}

function getVerdict(text: string): "bullish" | "bearish" | "neutral" | null {
  const lower = text.toLowerCase();
  const b = (lower.match(/bullish/g) || []).length;
  const r = (lower.match(/bearish/g) || []).length;
  const n = (lower.match(/neutral/g) || []).length;
  if (b > r && b > n) return "bullish";
  if (r > b) return "bearish";
  if (n > 0) return "neutral";
  return null;
}

// Skeleton row patterns that mimic real report structure
const SKELETON_ROWS = [
  { w: 40, h: 18, mb: 6  },  // h2 heading
  { w: 20, h: 10, mb: 14 },  // plugin label
  { w: 95, h: 13, mb: 5  },  // paragraph line
  { w: 88, h: 13, mb: 5  },
  { w: 72, h: 13, mb: 22 },  // end of paragraph
  { w: 38, h: 18, mb: 6  },  // h2 heading
  { w: 18, h: 10, mb: 14 },
  { w: 93, h: 13, mb: 5  },
  { w: 85, h: 13, mb: 5  },
  { w: 78, h: 13, mb: 5  },
  { w: 60, h: 13, mb: 22 },
  { w: 42, h: 18, mb: 6  },
  { w: 22, h: 10, mb: 14 },
  { w: 90, h: 13, mb: 5  },
  { w: 82, h: 13, mb: 5  },
];

export default function AIReport({ ticker, autoTrigger }: Props) {
  const [report,    setReport]    = useState("");
  const [loading,   setLoading]   = useState(false);
  const [error,     setError]     = useState<string | null>(null);
  const [generated, setGenerated] = useState(false);
  const abortRef        = useRef<AbortController | null>(null);
  const didAutoGenerate = useRef(false);
  const endRef          = useRef<HTMLDivElement>(null);

  useEffect(() => {
    didAutoGenerate.current = false;
    setReport(""); setGenerated(false); setError(null); setLoading(false);
    if (abortRef.current) { abortRef.current.abort(); abortRef.current = null; }
  }, [ticker]);

  useEffect(() => {
    if (autoTrigger && !didAutoGenerate.current) {
      didAutoGenerate.current = true;
      generate();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoTrigger, ticker]);

  useEffect(() => {
    if (!loading || !endRef.current) return;
    const scroller = endRef.current.closest("[data-scroll]") as HTMLElement | null;
    if (!scroller) return;
    const dist = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight;
    if (dist < 120) endRef.current.scrollIntoView({ block: "end" });
  }, [report, loading]);

  async function generate() {
    if (abortRef.current) abortRef.current.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setLoading(true); setError(null); setReport(""); setGenerated(false);
    try {
      const res = await fetch(`http://localhost:8000/api/stock/${ticker}/plugin-report`, { signal: ctrl.signal });
      if (!res.ok) { const j = await res.json(); throw new Error(j.detail || "Failed"); }
      const reader  = res.body!.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split("\n"); buf = lines.pop() ?? "";
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const payload = line.slice(6);
          if (payload === "[DONE]") { setGenerated(true); break; }
          try { const { text } = JSON.parse(payload); setReport(r => r + text); } catch {}
        }
      }
      setGenerated(true);
    } catch (e: unknown) {
      if ((e as Error).name === "AbortError") return;
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally { setLoading(false); }
  }

  const verdict = report ? getVerdict(report) : null;
  const verdictConfig = verdict === "bullish"
    ? { color: "#22c55e", bg: "rgba(34,197,94,0.1)",  border: "rgba(34,197,94,0.3)",  icon: <TrendingUp size={14} />,  label: "Bullish Outlook"  }
    : verdict === "bearish"
    ? { color: "#ef4444", bg: "rgba(239,68,68,0.1)",   border: "rgba(239,68,68,0.3)",  icon: <TrendingDown size={14} />, label: "Bearish Outlook"  }
    : verdict === "neutral"
    ? { color: "#f59e0b", bg: "rgba(245,158,11,0.1)",  border: "rgba(245,158,11,0.3)", icon: <Minus size={14} />,       label: "Neutral Outlook"  }
    : null;

  return (
    <div className="rounded-2xl flex flex-col overflow-hidden"
      style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>

      {/* ── Header ── */}
      <div className="px-7 py-4 border-b flex items-center justify-between gap-4"
        style={{ borderColor: "var(--border)", background: "var(--surface2)" }}>

        <div className="flex items-center gap-4 flex-wrap">
          {/* Title */}
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0"
              style={{ background: "linear-gradient(135deg, #8b5cf6, #3b82f6)" }}>
              <Sparkles size={15} color="#fff" />
            </div>
            <div>
              <div className="text-sm font-bold leading-tight" style={{ color: "var(--text)" }}>
                AI Research Report
              </div>
              <div className="text-[11px] leading-tight mt-0.5" style={{ color: "var(--muted)" }}>
                {ticker} · Full initiation of coverage
              </div>
            </div>
          </div>

          {/* Divider */}
          <div className="w-px h-8 flex-shrink-0" style={{ background: "var(--border)" }} />

          {/* Plugin dots */}
          <div className="flex items-center gap-1.5">
            {(Object.entries(PLUGINS) as [Plugin, typeof PLUGINS[Plugin]][]).map(([key, { color, label }]) => (
              <span key={key} title={label}
                className="flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full font-medium"
                style={{ background: `${color}12`, color, border: `1px solid ${color}25` }}>
                <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ background: color }} />
                {label}
              </span>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-2.5 flex-shrink-0">
          {/* Status */}
          {loading && (
            <span className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full font-medium"
              style={{ background: "rgba(139,92,246,0.1)", color: "#a78bfa", border: "1px solid rgba(139,92,246,0.2)" }}>
              <RefreshCw size={11} className="animate-spin" />
              Generating…
            </span>
          )}
          {verdictConfig && !loading && (
            <span className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full font-semibold"
              style={{ background: verdictConfig.bg, color: verdictConfig.color, border: `1px solid ${verdictConfig.border}` }}>
              {verdictConfig.icon}
              {verdictConfig.label}
            </span>
          )}

          {/* Generate button */}
          <button onClick={generate} disabled={loading}
            className="flex items-center gap-2 text-xs px-4 py-2 rounded-xl font-semibold transition-all hover:opacity-85 disabled:opacity-40"
            style={{
              background: generated
                ? "var(--surface)"
                : "linear-gradient(135deg, #8b5cf6, #3b82f6)",
              color: generated ? "var(--muted2)" : "#fff",
              border: generated ? "1px solid var(--border2)" : "none",
              boxShadow: generated ? "none" : "0 2px 12px rgba(139,92,246,0.35)",
            }}>
            {generated ? <RotateCcw size={12} /> : <Sparkles size={12} />}
            {generated ? "Regenerate" : "Generate Report"}
          </button>
        </div>
      </div>

      {/* ── Body ── */}
      <div className="px-8 py-7">

        {/* Error */}
        {error && (
          <div className="text-sm rounded-xl px-4 py-3 mb-5"
            style={{ background: "rgba(239,68,68,0.08)", color: "var(--red)", border: "1px solid rgba(239,68,68,0.2)" }}>
            {error}
          </div>
        )}

        {/* ── Empty state ── */}
        {!report && !loading && !error && (
          <div className="flex flex-col items-center justify-center py-16 gap-7">
            {/* Glow icon */}
            <div className="relative">
              <div className="absolute inset-0 rounded-3xl blur-2xl"
                style={{ background: "linear-gradient(135deg, rgba(139,92,246,0.35), rgba(59,130,246,0.35))", transform: "scale(1.4)" }} />
              <div className="relative w-20 h-20 rounded-3xl flex items-center justify-center"
                style={{ background: "linear-gradient(135deg, #8b5cf6, #3b82f6)", boxShadow: "0 8px 32px rgba(139,92,246,0.4)" }}>
                <Sparkles size={32} color="#fff" />
              </div>
            </div>

            <div className="text-center flex flex-col gap-2 max-w-md">
              <div className="text-xl font-bold" style={{ color: "var(--text)" }}>
                Full Initiation-of-Coverage Report
              </div>
              <div className="text-sm leading-relaxed" style={{ color: "var(--muted)" }}>
                Runs all 4 research plugins in sequence — equity thesis, DCF model,
                comparable companies, earnings quality, and sector context.
              </div>
            </div>

            {/* Plugin grid */}
            <div className="grid grid-cols-2 gap-3 w-full max-w-md">
              {(Object.entries(PLUGINS) as [Plugin, typeof PLUGINS[Plugin]][]).map(([key, { color, label }]) => (
                <div key={key} className="flex items-center gap-3 px-4 py-3 rounded-xl"
                  style={{ background: `${color}0e`, border: `1px solid ${color}28` }}>
                  <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: color }} />
                  <span className="text-sm font-medium" style={{ color }}>{label}</span>
                </div>
              ))}
            </div>

            <button onClick={generate}
              className="flex items-center gap-2.5 px-8 py-3.5 rounded-2xl text-base font-bold transition-all hover:opacity-90 hover:scale-[1.02] active:scale-[0.99]"
              style={{
                background: "linear-gradient(135deg, #8b5cf6, #3b82f6)",
                color: "#fff",
                boxShadow: "0 6px 28px rgba(139,92,246,0.4)",
              }}>
              <Sparkles size={17} />
              Generate Full Report
            </button>
          </div>
        )}

        {/* ── Skeleton ── */}
        {loading && !report && (
          <div className="flex flex-col py-2">
            {SKELETON_ROWS.map((row, i) => (
              <div key={i} className="animate-pulse rounded-full"
                style={{
                  background: "var(--surface2)",
                  height: row.h,
                  width: `${row.w}%`,
                  marginBottom: row.mb,
                  animationDelay: `${i * 0.06}s`,
                  borderRadius: row.h >= 16 ? 6 : 999,
                }} />
            ))}
          </div>
        )}

        {/* ── Report ── */}
        {report && (
          <div>
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{

                h2: ({ children }) => {
                  const plug = getPlugin(String(children));
                  const { color, label } = PLUGINS[plug];
                  return (
                    <div className="mt-12 mb-5 first:mt-0">
                      {/* Section card header */}
                      <div className="flex items-center gap-2 mb-3">
                        <span className="w-2 h-2 rounded-full" style={{ background: color }} />
                        <span className="text-xs font-bold uppercase tracking-[0.12em]" style={{ color }}>
                          {label}
                        </span>
                        <div className="flex-1 h-px ml-1" style={{ background: `linear-gradient(90deg, ${color}30, transparent)` }} />
                      </div>
                      <h2 className="text-xl font-bold leading-snug" style={{ color: "var(--text)" }}>
                        {children}
                      </h2>
                    </div>
                  );
                },

                h3: ({ children }) => (
                  <h3 className="text-[13px] font-bold uppercase tracking-[0.08em] mt-6 mb-3"
                    style={{ color: "var(--muted2)" }}>
                    {children}
                  </h3>
                ),

                p: ({ children }) => (
                  <p className="mb-4 text-[15px] leading-[1.85]"
                    style={{ color: "var(--text)", opacity: 0.92 }}>
                    {children}
                  </p>
                ),

                ul: ({ children }) => (
                  <ul className="mb-4 flex flex-col gap-2.5 pl-1">{children}</ul>
                ),

                ol: ({ children }) => (
                  <ol className="mb-4 flex flex-col gap-2.5 list-decimal pl-5">{children}</ol>
                ),

                li: ({ children }) => (
                  <li className="flex gap-3 items-start text-[15px] leading-[1.8]">
                    <span className="mt-[9px] w-[5px] h-[5px] rounded-full flex-shrink-0"
                      style={{ background: "var(--muted2)" }} />
                    <span style={{ color: "var(--text)", opacity: 0.92 }}>{children}</span>
                  </li>
                ),

                strong: ({ children }) => (
                  <strong className="font-semibold" style={{ color: "var(--text)" }}>{children}</strong>
                ),

                em: ({ children }) => (
                  <em className="italic" style={{ color: "var(--muted2)" }}>{children}</em>
                ),

                table: ({ children }) => (
                  <div className="overflow-x-auto my-6 rounded-xl border"
                    style={{ borderColor: "var(--border)" }}>
                    <table className="w-full border-collapse">{children}</table>
                  </div>
                ),

                thead: ({ children }) => <thead>{children}</thead>,
                tbody: ({ children }) => <tbody>{children}</tbody>,

                th: ({ children }) => (
                  <th className="px-5 py-3 text-left font-semibold text-xs uppercase tracking-wider border-b"
                    style={{
                      borderColor: "var(--border)",
                      background: "var(--surface2)",
                      color: "var(--muted2)",
                    }}>
                    {children}
                  </th>
                ),

                tr: ({ children, ...props }) => {
                  // @ts-ignore
                  const isEven = (props.node?.position?.start?.line ?? 0) % 2 === 0;
                  return (
                    <tr style={{ background: isEven ? "rgba(255,255,255,0.02)" : "transparent" }}>
                      {children}
                    </tr>
                  );
                },

                td: ({ children }) => (
                  <td className="px-5 py-3.5 border-b text-[14px]"
                    style={{ borderColor: "var(--border)", color: "var(--text)", opacity: 0.9 }}>
                    {children}
                  </td>
                ),

                blockquote: ({ children }) => (
                  <blockquote className="border-l-[3px] pl-5 my-5 py-1"
                    style={{
                      borderColor: "#8b5cf6",
                      background: "rgba(139,92,246,0.05)",
                      borderRadius: "0 8px 8px 0",
                    }}>
                    {children}
                  </blockquote>
                ),

                code: ({ children }) => (
                  <code className="px-2 py-0.5 rounded-md text-[13px] font-mono"
                    style={{ background: "rgba(139,92,246,0.1)", color: "#c4b5fd" }}>
                    {children}
                  </code>
                ),

                hr: () => (
                  <hr className="my-8 border-0 h-px" style={{ background: "var(--border)" }} />
                ),
              }}
            >
              {report}
            </ReactMarkdown>

            {loading && (
              <span className="inline-block w-[3px] h-[16px] rounded-sm ml-0.5 align-middle animate-pulse"
                style={{ background: "#8b5cf6" }} />
            )}

            <div ref={endRef} />
          </div>
        )}
      </div>
    </div>
  );
}
