"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { Sparkles, RefreshCw, RotateCcw } from "lucide-react";

interface Props { ticker: string; autoTrigger?: boolean }

export default function AIReport({ ticker, autoTrigger }: Props) {
  const [html,      setHtml]      = useState("");
  const [loading,   setLoading]   = useState(false);
  const [error,     setError]     = useState<string | null>(null);
  const [generated, setGenerated] = useState(false);
  const abortRef        = useRef<AbortController | null>(null);
  const didAutoGenerate = useRef(false);
  const iframeRef       = useRef<HTMLIFrameElement>(null);

  useEffect(() => {
    didAutoGenerate.current = false;
    setHtml(""); setGenerated(false); setError(null); setLoading(false);
    if (abortRef.current) { abortRef.current.abort(); abortRef.current = null; }
  }, [ticker]);

  useEffect(() => {
    if (autoTrigger && !didAutoGenerate.current) {
      didAutoGenerate.current = true;
      generate();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoTrigger, ticker]);

  const autoSizeIframe = useCallback(() => {
    const iframe = iframeRef.current;
    if (!iframe || !iframe.contentDocument?.body) return;
    const h = iframe.contentDocument.documentElement.scrollHeight;
    iframe.style.height = h + "px";
  }, []);

  async function generate() {
    if (abortRef.current) abortRef.current.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setLoading(true); setError(null); setHtml(""); setGenerated(false);
    try {
      const res = await fetch(`http://localhost:8000/api/stock/${ticker}/report`, {
        signal: ctrl.signal,
      });
      if (!res.ok) {
        const j = await res.json().catch(() => ({}));
        throw new Error(j.detail || `HTTP ${res.status}`);
      }
      const reader  = res.body!.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      let accumulated = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split("\n"); buf = lines.pop() ?? "";
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const payload = line.slice(6);
          if (payload === "[DONE]") { setHtml(accumulated); setGenerated(true); break; }
          try { const { text } = JSON.parse(payload); accumulated += text; } catch {}
        }
      }
      if (!accumulated) throw new Error("Empty response from server");
    } catch (e: unknown) {
      if ((e as Error).name === "AbortError") return;
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  const SKELETON_ROWS = [
    { w: 40, h: 18, mb: 6  },
    { w: 20, h: 10, mb: 14 },
    { w: 95, h: 13, mb: 5  },
    { w: 88, h: 13, mb: 5  },
    { w: 72, h: 13, mb: 22 },
    { w: 38, h: 18, mb: 6  },
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

  return (
    <div className="rounded-2xl flex flex-col overflow-hidden"
      style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>

      {/* ── Header ── */}
      <div className="px-7 py-4 border-b flex items-center justify-between gap-4"
        style={{ borderColor: "var(--border)", background: "var(--surface2)" }}>

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
              {ticker} · Institutional equity analysis
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2.5">
          {loading && (
            <span className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full font-medium"
              style={{ background: "rgba(139,92,246,0.1)", color: "#a78bfa", border: "1px solid rgba(139,92,246,0.2)" }}>
              <RefreshCw size={11} className="animate-spin" />
              Analysing… this takes ~60s
            </span>
          )}

          <button onClick={generate} disabled={loading}
            className="flex items-center gap-2 text-xs px-4 py-2 rounded-xl font-semibold transition-all hover:opacity-85 disabled:opacity-40"
            style={{
              background: generated ? "var(--surface)" : "linear-gradient(135deg, #8b5cf6, #3b82f6)",
              color:      generated ? "var(--muted2)" : "#fff",
              border:     generated ? "1px solid var(--border2)" : "none",
              boxShadow:  generated ? "none" : "0 2px 12px rgba(139,92,246,0.35)",
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

        {/* Empty state */}
        {!html && !loading && !error && (
          <div className="flex flex-col items-center justify-center py-16 gap-7">
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
                Generates a complete institutional equity research report — valuation,
                moat analysis, technicals, risks, conviction scorecard, and scenarios.
                Takes about 60 seconds.
              </div>
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

        {/* Skeleton */}
        {loading && (
          <div className="flex flex-col py-2">
            {SKELETON_ROWS.map((row, i) => (
              <div key={i} className="animate-pulse"
                style={{
                  background:       "var(--surface2)",
                  height:           row.h,
                  width:            `${row.w}%`,
                  marginBottom:     row.mb,
                  animationDelay:   `${i * 0.06}s`,
                  borderRadius:     row.h >= 16 ? 6 : 999,
                }} />
            ))}
          </div>
        )}

        {/* HTML report rendered in sandboxed iframe */}
        {html && !loading && (
          <iframe
            ref={iframeRef}
            srcDoc={html}
            title={`${ticker} AI Research Report`}
            sandbox="allow-same-origin"
            style={{
              width:        "100%",
              minHeight:    600,
              border:       "none",
              borderRadius: 8,
              display:      "block",
            }}
            onLoad={autoSizeIframe}
          />
        )}
      </div>
    </div>
  );
}
