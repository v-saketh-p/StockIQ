"use client";

import { useState, useRef, useEffect } from "react";
import { X, Send, Sparkles, RefreshCw, ChevronRight } from "lucide-react";
import { API_BASE } from "@/lib/api";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface Message {
  role: "user" | "assistant";
  content: string;       // cleaned content (no ===FOLLOWUPS=== block)
  followups?: string[];  // parsed follow-up chips
  streaming?: boolean;
}

interface Props {
  ticker: string;
  companyName: string;
  onClose: () => void;
}

const INITIAL_SUGGESTIONS = [
  "Is this stock overvalued right now?",
  "What's the bull case for this stock?",
  "What are the biggest risks I should know?",
  "How does the valuation compare historically?",
  "What do the technicals suggest?",
  "Should I buy, hold, or sell?",
];

const FALLBACK_FOLLOWUPS = [
  "What are the biggest risks right now?",
  "Is the valuation cheap or expensive?",
  "What do the technicals say?",
  "How's the revenue growth trending?",
  "What's the bull case?",
  "What's the bear case?",
  "How profitable is this company?",
  "How much debt does it have?",
  "Is momentum bullish or bearish?",
  "What's the free cash flow like?",
  "How does it compare to competitors?",
  "Is this a good entry point?",
];

// Parse ===FOLLOWUPS=== block out of raw AI text
function parseFollowups(raw: string): { content: string; followups: string[] } {
  // Match ===FOLLOWUPS=== even if the model wraps it with extra = signs or whitespace
  const match = raw.match(/=+FOLLOWUPS=+/);
  if (!match || match.index === undefined) return { content: raw.trim(), followups: [] };
  const content = raw.slice(0, match.index).trim();
  const block   = raw.slice(match.index + match[0].length).trim();
  const followups = block
    .split("\n")
    .map(l => l.replace(/^[-•*\d.]+\s*/, "").trim())
    .filter(l => l.length > 4 && l.includes(" "));
  return { content, followups: followups.slice(0, 3) };
}

function MarkdownMessage({ text }: { text: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        p:      ({ children }) => <p className="mb-2 last:mb-0 leading-relaxed">{children}</p>,
        strong: ({ children }) => <strong className="font-bold" style={{ color: "var(--text)" }}>{children}</strong>,
        em:     ({ children }) => <em className="italic">{children}</em>,
        ul:     ({ children }) => <ul className="list-disc list-inside mb-2 flex flex-col gap-0.5">{children}</ul>,
        ol:     ({ children }) => <ol className="list-decimal list-inside mb-2 flex flex-col gap-0.5">{children}</ol>,
        li:     ({ children }) => <li className="leading-relaxed">{children}</li>,
        h1:     ({ children }) => <h1 className="text-sm font-bold mb-1 mt-2" style={{ color: "var(--text)" }}>{children}</h1>,
        h2:     ({ children }) => <h2 className="text-sm font-bold mb-1 mt-2" style={{ color: "var(--text)" }}>{children}</h2>,
        h3:     ({ children }) => <h3 className="text-xs font-bold mb-1 mt-1.5" style={{ color: "var(--text)" }}>{children}</h3>,
        code:   ({ children }) => (
          <code className="px-1.5 py-0.5 rounded text-xs font-mono"
            style={{ background: "rgba(59,130,246,0.12)", color: "var(--blue)" }}>
            {children}
          </code>
        ),
        blockquote: ({ children }) => (
          <blockquote className="border-l-2 pl-3 italic my-1"
            style={{ borderColor: "var(--blue)", color: "var(--muted)" }}>
            {children}
          </blockquote>
        ),
        table: ({ children }) => (
          <div className="overflow-x-auto my-2">
            <table className="text-xs w-full border-collapse">{children}</table>
          </div>
        ),
        th: ({ children }) => (
          <th className="px-2 py-1 text-left font-semibold border-b"
            style={{ borderColor: "var(--border)", color: "var(--muted)" }}>
            {children}
          </th>
        ),
        td: ({ children }) => (
          <td className="px-2 py-1 border-b"
            style={{ borderColor: "var(--border)", color: "var(--text)" }}>
            {children}
          </td>
        ),
      }}
    >
      {text}
    </ReactMarkdown>
  );
}

export default function ChatPanel({ ticker, companyName, onClose }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input,    setInput]    = useState("");
  const [loading,  setLoading]  = useState(false);
  const bottomRef  = useRef<HTMLDivElement>(null);
  const inputRef   = useRef<HTMLTextAreaElement>(null);
  const abortRef   = useRef<AbortController | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  // Auto-grow textarea
  function handleInput(e: React.ChangeEvent<HTMLTextAreaElement>) {
    setInput(e.target.value);
    e.target.style.height = "auto";
    e.target.style.height = Math.min(e.target.scrollHeight, 120) + "px";
  }

  async function send(text: string) {
    if (!text.trim() || loading) return;

    const userMsg: Message = { role: "user", content: text.trim() };
    const history = [...messages, userMsg];
    setMessages([...history, { role: "assistant", content: "", streaming: true }]);
    setInput("");
    if (inputRef.current) inputRef.current.style.height = "auto";
    setLoading(true);

    if (abortRef.current) abortRef.current.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    let raw = "";

    try {
      const res = await fetch(`${API_BASE}/api/stock/${ticker}/chat`, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ messages: history.map(m => ({ role: m.role, content: m.content })) }),
        signal:  ctrl.signal,
      });
      if (!res.ok) throw new Error("Failed");

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
          if (payload === "[DONE]") break;
          try {
            const { text: chunk } = JSON.parse(payload);
            raw += chunk;
            // Stream the visible part only (hide ===FOLLOWUPS=== block while typing)
            const fMatch     = raw.match(/=+FOLLOWUPS=+/);
            const visibleEnd = fMatch?.index ?? -1;
            const visible    = visibleEnd === -1 ? raw : raw.slice(0, visibleEnd);
            setMessages(prev => {
              const updated = [...prev];
              const last    = updated[updated.length - 1];
              if (last.role === "assistant") last.content = visible;
              return updated;
            });
          } catch {}
        }
      }
    } catch (e) {
      if ((e as Error).name === "AbortError") return;
      raw = "Sorry, something went wrong. Please try again.";
    } finally {
      // Parse final response and attach follow-ups
      const { content, followups } = parseFollowups(raw);
      setMessages(prev => {
        const updated = [...prev];
        const last    = updated[updated.length - 1];
        if (last.role === "assistant") {
          last.content   = content || raw;
          last.followups = followups;
          last.streaming = false;
        }
        return updated;
      });
      setLoading(false);
    }
  }

  function clearChat() {
    if (abortRef.current) abortRef.current.abort();
    setMessages([]);
    setLoading(false);
  }

  return (
    <div
      className="fixed right-0 top-0 h-screen flex flex-col z-50"
      style={{
        width: 420,
        background: "var(--surface)",
        borderLeft: "1px solid var(--border)",
        boxShadow: "-12px 0 40px var(--shadow)",
        animation: "slideIn 0.25s cubic-bezier(0.34,1.1,0.64,1)",
      }}
    >
      <style>{`
        @keyframes slideIn {
          from { transform: translateX(100%); opacity: 0; }
          to   { transform: translateX(0);    opacity: 1; }
        }
        .chat-prose { font-size: 13px; color: var(--text); line-height: 1.6; }
      `}</style>

      {/* ── Header ── */}
      <div className="flex items-center justify-between px-4 py-3 flex-shrink-0 border-b"
        style={{ background: "var(--surface2)", borderColor: "var(--border)" }}>
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-xl flex items-center justify-center"
            style={{ background: "linear-gradient(135deg,#3b82f6,#8b5cf6)" }}>
            <Sparkles size={14} style={{ color: "#fff" }} />
          </div>
          <div>
            <div className="text-sm font-bold" style={{ color: "var(--text)" }}>AI Research Assistant</div>
            <div className="flex items-center gap-1.5 text-xs" style={{ color: "var(--muted)" }}>
              <span className="w-1.5 h-1.5 rounded-full" style={{ background: "var(--green)" }} />
              {ticker} · {companyName}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-1">
          {messages.length > 0 && (
            <button onClick={clearChat} title="Clear chat"
              className="p-1.5 rounded-lg hover:opacity-70 transition-opacity"
              style={{ color: "var(--muted)" }}>
              <RefreshCw size={13} />
            </button>
          )}
          <button onClick={onClose}
            className="p-1.5 rounded-lg hover:opacity-70 transition-opacity"
            style={{ color: "var(--muted)" }}>
            <X size={15} />
          </button>
        </div>
      </div>

      {/* ── Messages ── */}
      <div className="flex-1 overflow-y-auto px-4 py-4 flex flex-col gap-4">

        {/* Empty state */}
        {messages.length === 0 && (
          <div className="flex flex-col gap-5">
            <div className="flex flex-col items-center gap-2 py-4">
              <div className="w-14 h-14 rounded-2xl flex items-center justify-center"
                style={{ background: "linear-gradient(135deg,rgba(59,130,246,0.15),rgba(139,92,246,0.15))" }}>
                <Sparkles size={22} style={{ color: "var(--blue)" }} />
              </div>
              <div className="text-sm font-semibold text-center" style={{ color: "var(--text)" }}>
                Ask anything about {ticker}
              </div>
              <div className="text-xs text-center max-w-[260px]" style={{ color: "var(--muted)" }}>
                I have live access to price, fundamentals, technicals, and market data.
              </div>
            </div>
            <div className="flex flex-col gap-1.5">
              <div className="text-xs font-semibold uppercase tracking-widest px-1 mb-1"
                style={{ color: "var(--muted)" }}>Suggested questions</div>
              {INITIAL_SUGGESTIONS.map((s, i) => (
                <button key={i} onClick={() => send(s)}
                  className="text-left text-xs px-3.5 py-2.5 rounded-xl border flex items-center justify-between group transition-all hover:border-[rgba(59,130,246,0.3)]"
                  style={{ background: "var(--surface2)", borderColor: "var(--border)", color: "var(--text)" }}>
                  <span>{s}</span>
                  <ChevronRight size={12} className="opacity-0 group-hover:opacity-60 transition-opacity flex-shrink-0 ml-2"
                    style={{ color: "var(--muted)" }} />
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Message bubbles */}
        {messages.map((msg, i) => (
          <div key={i} className="flex flex-col gap-2">
            <div className={`flex gap-2.5 ${msg.role === "user" ? "flex-row-reverse" : "flex-row"}`}>
              {/* AI avatar */}
              {msg.role === "assistant" && (
                <div className="w-7 h-7 rounded-lg flex-shrink-0 flex items-center justify-center mt-0.5"
                  style={{ background: "linear-gradient(135deg,#3b82f6,#8b5cf6)" }}>
                  <Sparkles size={11} style={{ color: "#fff" }} />
                </div>
              )}

              <div
                className="max-w-[88%] rounded-2xl px-4 py-3"
                style={{
                  background: msg.role === "user"
                    ? "linear-gradient(135deg,#3b82f6,#2563eb)"
                    : "var(--surface2)",
                  color: msg.role === "user" ? "#fff" : "var(--text)",
                  borderBottomRightRadius: msg.role === "user"      ? 4 : undefined,
                  borderBottomLeftRadius:  msg.role === "assistant" ? 4 : undefined,
                  border: msg.role === "assistant" ? "1px solid var(--border)" : "none",
                }}
              >
                {msg.role === "user" ? (
                  <span className="text-xs leading-relaxed">{msg.content}</span>
                ) : msg.content ? (
                  <div className="chat-prose">
                    <MarkdownMessage text={msg.content} />
                    {msg.streaming && (
                      <span className="inline-block w-1.5 h-3.5 ml-0.5 rounded-sm animate-pulse align-middle"
                        style={{ background: "var(--blue)" }} />
                    )}
                  </div>
                ) : msg.streaming ? (
                  <span className="flex gap-1 items-center py-1">
                    {[0,1,2].map(j => (
                      <span key={j} className="w-1.5 h-1.5 rounded-full animate-bounce"
                        style={{ background: "var(--muted)", animationDelay: `${j * 0.15}s` }} />
                    ))}
                  </span>
                ) : null}
              </div>
            </div>

            {/* Follow-up suggestion chips — always shown after every AI response */}
            {msg.role === "assistant" && !msg.streaming && msg.content && (() => {
              const chips = (msg.followups && msg.followups.length > 0)
                ? msg.followups
                : FALLBACK_FOLLOWUPS.slice((i * 3) % FALLBACK_FOLLOWUPS.length, (i * 3) % FALLBACK_FOLLOWUPS.length + 3);
              return (
                <div className="flex flex-col gap-1.5 ml-9">
                  <div className="text-xs" style={{ color: "var(--muted)", opacity: 0.7 }}>Follow-up questions</div>
                  {chips.map((q, j) => (
                    <button key={j} onClick={() => send(q)}
                      className="text-left text-xs px-3 py-2 rounded-xl border flex items-center justify-between group transition-all hover:border-[rgba(59,130,246,0.35)]"
                      style={{ background: "var(--surface)", borderColor: "var(--border)", color: "var(--text)" }}>
                      <span>{q}</span>
                      <ChevronRight size={11} className="opacity-0 group-hover:opacity-60 transition-opacity flex-shrink-0 ml-2"
                        style={{ color: "var(--muted)" }} />
                    </button>
                  ))}
                </div>
              );
            })()}
          </div>
        ))}

        <div ref={bottomRef} />
      </div>

      {/* ── Input ── */}
      <div className="flex-shrink-0 px-4 py-3 border-t" style={{ borderColor: "var(--border)" }}>
        <div className="rounded-2xl border flex items-end gap-2 px-3.5 py-2.5 transition-colors"
          style={{ background: "var(--surface2)", borderColor: "var(--border)" }}>
          <textarea
            ref={inputRef}
            value={input}
            onChange={handleInput}
            onKeyDown={e => {
              if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input); }
            }}
            placeholder={`Ask about ${ticker}… (Shift+Enter for new line)`}
            rows={1}
            className="flex-1 bg-transparent outline-none text-xs resize-none leading-relaxed"
            style={{ color: "var(--text)", minHeight: 20, maxHeight: 120 }}
            disabled={loading}
          />
          <button
            onClick={() => send(input)}
            disabled={!input.trim() || loading}
            className="w-7 h-7 rounded-xl flex items-center justify-center flex-shrink-0 transition-all disabled:opacity-30"
            style={{ background: "var(--blue)", color: "#fff" }}
          >
            {loading
              ? <RefreshCw size={12} className="animate-spin" />
              : <Send size={12} />
            }
          </button>
        </div>
        <div className="text-xs mt-1.5 text-center" style={{ color: "var(--muted)", opacity: 0.5 }}>
          AI may make mistakes · verify before investing
        </div>
      </div>
    </div>
  );
}
