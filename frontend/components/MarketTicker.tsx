"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { API_BASE } from "@/lib/api";

interface IndexItem {
  symbol: string;
  name: string;
  format: string;
  price: number;
  change: number;
  changePct: number;
  marketStatus: string;
  extendedPrice?: number;
  extendedChangePct?: number;
  extendedSession?: string;
}

function fmtPrice(price: number, format: string): string {
  if (format === "yield") return price.toFixed(3) + "%";
  if (price >= 1000)
    return price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return price.toFixed(2);
}

function StatusDot({ status }: { status: string }) {
  const map: Record<string, { label: string; bg: string; dot: string }> = {
    open:   { label: "LIVE",   bg: "rgba(34,197,94,0.15)",   dot: "#22c55e" },
    pre:    { label: "PRE",    bg: "rgba(59,130,246,0.15)",  dot: "#60a5fa" },
    post:   { label: "AFTER",  bg: "rgba(245,158,11,0.15)",  dot: "#f59e0b" },
    closed: { label: "CLOSED", bg: "rgba(100,100,120,0.15)", dot: "#666688" },
  };
  const s = map[status] ?? map.closed;
  return (
    <span
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold flex-shrink-0"
      style={{ background: s.bg, border: `1px solid ${s.dot}44`, color: s.dot }}
    >
      <span
        className="w-1.5 h-1.5 rounded-full"
        style={{ background: s.dot, boxShadow: status === "open" ? `0 0 5px ${s.dot}` : "none" }}
      />
      {s.label}
    </span>
  );
}

function TickerItem({ item }: { item: IndexItem }) {
  const up    = item.changePct >= 0;
  const extUp = (item.extendedChangePct ?? 0) >= 0;

  return (
    <span
      className="inline-flex items-center gap-2 px-5 whitespace-nowrap text-[11px]"
      style={{ borderRight: "1px solid var(--border)" }}
    >
      <span style={{ color: "var(--muted2)", fontWeight: 500 }}>{item.name}</span>
      <span style={{ color: "var(--text)", fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>
        {fmtPrice(item.price, item.format)}
      </span>
      <span
        style={{
          color: up ? "var(--green)" : "var(--red)",
          fontWeight: 700,
          fontVariantNumeric: "tabular-nums",
        }}
      >
        {up ? "▲" : "▼"} {Math.abs(item.changePct).toFixed(2)}%
      </span>
      {item.extendedSession && item.extendedPrice != null && (
        <span
          className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold"
          style={{
            background: "rgba(96,165,250,0.12)",
            border: "1px solid rgba(96,165,250,0.25)",
            color: "#93c5fd",
            fontVariantNumeric: "tabular-nums",
          }}
        >
          {item.extendedSession}
          <span>{fmtPrice(item.extendedPrice, item.format)}</span>
          <span style={{ color: extUp ? "#86efac" : "#fca5a5" }}>
            {extUp ? "▲" : "▼"} {Math.abs(item.extendedChangePct ?? 0).toFixed(2)}%
          </span>
        </span>
      )}
    </span>
  );
}

// ~24 px/s at 60 fps
const SPEED = 0.4;

export default function MarketTicker() {
  const [indices, setIndices]     = useState<IndexItem[]>([]);
  const [marketStatus, setStatus] = useState("closed");

  // Viewport (clipping container) and inner track (what we translate)
  const viewportRef = useRef<HTMLDivElement>(null);
  const trackRef    = useRef<HTMLDivElement>(null);

  // Runtime state held in refs so the RAF loop never needs to trigger renders
  const isHovered = useRef(false);
  const rafId     = useRef(0);
  const offset    = useRef(0);   // current translateX in px (always ≤ 0)

  // Drag state
  const dragging   = useRef(false);
  const dragX      = useRef(0);
  const dragOffset = useRef(0);

  // ── Fetch ──────────────────────────────────────────────────────────────────
  const fetchIndices = useCallback(async () => {
    try {
      const res  = await fetch(`${API_BASE}/api/market/indices`);
      if (!res.ok) return;
      const data: IndexItem[] = await res.json();
      if (Array.isArray(data) && data.length > 0) {
        setIndices(data);
        setStatus(data[0]?.marketStatus ?? "closed");
      }
    } catch { /* non-critical */ }
  }, []);

  useEffect(() => {
    fetchIndices();
    const id = setInterval(fetchIndices, 30_000);
    return () => clearInterval(id);
  }, [fetchIndices]);

  // ── RAF auto-scroll via CSS transform ─────────────────────────────────────
  // We use transform (not scrollLeft) because transform works unconditionally —
  // it doesn't depend on overflow CSS values being computed correctly.
  useEffect(() => {
    if (indices.length === 0) return;

    // Wait one frame so the track has been laid out and offsetWidth is real
    const startId = requestAnimationFrame(() => {
      const track = trackRef.current;
      if (!track) return;

      const tick = () => {
        const halfW = track.offsetWidth / 2;

        if (!isHovered.current && halfW > 0) {
          offset.current -= SPEED;
        }

        // Seamless loop in both directions
        if (halfW > 0) {
          while (offset.current <= -halfW) offset.current += halfW;
          while (offset.current  >  0)    offset.current -= halfW;
        }

        track.style.transform = `translateX(${offset.current}px)`;
        rafId.current = requestAnimationFrame(tick);
      };

      rafId.current = requestAnimationFrame(tick);
    });

    return () => {
      cancelAnimationFrame(startId);
      cancelAnimationFrame(rafId.current);
    };
  }, [indices]);

  // ── Wheel → horizontal scroll (non-passive) ────────────────────────────────
  useEffect(() => {
    const vp = viewportRef.current;
    if (!vp) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      offset.current -= e.deltaX !== 0 ? e.deltaX : e.deltaY;
    };
    vp.addEventListener("wheel", onWheel, { passive: false });
    return () => vp.removeEventListener("wheel", onWheel);
  }, []);   // viewport never unmounts — [] is fine here

  // ── Mouse event handlers ───────────────────────────────────────────────────
  const onMouseEnter = () => { isHovered.current = true; };
  const onMouseLeave = () => { isHovered.current = false; dragging.current = false; };

  const onMouseDown = (e: React.MouseEvent) => {
    dragging.current = true;
    dragX.current     = e.clientX;
    dragOffset.current = offset.current;
    e.preventDefault();
  };
  const onMouseMove = (e: React.MouseEvent) => {
    if (!dragging.current) return;
    offset.current = dragOffset.current + (e.clientX - dragX.current);
  };
  const onMouseUp = () => { dragging.current = false; };

  // ── Touch handlers ─────────────────────────────────────────────────────────
  const touchX      = useRef(0);
  const touchOffset = useRef(0);
  const onTouchStart = (e: React.TouchEvent) => {
    touchX.current      = e.touches[0].clientX;
    touchOffset.current = offset.current;
    isHovered.current   = true;
  };
  const onTouchMove = (e: React.TouchEvent) => {
    offset.current = touchOffset.current + (e.touches[0].clientX - touchX.current);
  };
  const onTouchEnd = () => { isHovered.current = false; };

  if (indices.length === 0) return null;

  // Duplicate items so the track is always at least 2× the viewport width
  const items = [...indices, ...indices];

  return (
    <div
      style={{
        height: 34,
        background: "var(--surface3)",
        borderBottom: "1px solid var(--border)",
        display: "flex",
        alignItems: "center",
        flexShrink: 0,
        overflow: "hidden",
        userSelect: "none",
      }}
    >
      {/* Session badge */}
      <div
        className="flex items-center px-3 flex-shrink-0"
        style={{ borderRight: "1px solid var(--border2)", height: "100%" }}
      >
        <StatusDot status={marketStatus} />
      </div>

      {/* Clipping viewport */}
      <div
        ref={viewportRef}
        className="ticker-viewport"
        style={{ flex: 1, minWidth: 0, height: "100%", overflow: "hidden" }}
        onMouseEnter={onMouseEnter}
        onMouseLeave={onMouseLeave}
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={onMouseUp}
        onTouchStart={onTouchStart}
        onTouchMove={onTouchMove}
        onTouchEnd={onTouchEnd}
      >
        {/* Moving track — translateX drives all motion */}
        <div
          ref={trackRef}
          style={{
            display: "inline-flex",
            alignItems: "center",
            height: 34,
            willChange: "transform",
          }}
        >
          {items.map((item, i) => (
            <TickerItem key={`${item.symbol}-${i}`} item={item} />
          ))}
        </div>
      </div>
    </div>
  );
}
