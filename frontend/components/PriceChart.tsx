"use client";

import { useEffect, useRef, useState } from "react";
import { useTheme } from "./ThemeProvider";

declare global {
  interface Window {
    TradingView?: {
      widget: new (config: Record<string, unknown>) => { remove?: () => void };
    };
  }
}

let _counter = 0;

interface Props {
  ticker: string;
  ma50?: number;
  ma200?: number;
}

export default function PriceChart({ ticker }: Props) {
  const idRef      = useRef(`tv_${++_counter}`);
  const overlayRef = useRef<HTMLDivElement>(null);
  const [active,  setActive]  = useState(false);
  const [hovered, setHovered] = useState(false);
  const { theme } = useTheme();

  function handleWheel(e: React.WheelEvent) {
    let el = overlayRef.current?.parentElement;
    while (el) {
      const { overflowY } = window.getComputedStyle(el);
      if (overflowY === "auto" || overflowY === "scroll") {
        el.scrollTop += e.deltaY;
        return;
      }
      el = el.parentElement;
    }
  }

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setActive(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    const id = idRef.current;

    function init() {
      if (!window.TradingView || !document.getElementById(id)) return;
      new window.TradingView.widget({
        autosize:            true,
        symbol:              ticker.toUpperCase(),
        interval:            "D",
        timezone:            "America/New_York",
        theme:               theme === "light" ? "light" : "dark",
        style:               "1",
        locale:              "en",
        toolbar_bg:          theme === "light" ? "#ffffff" : "#0d0d14",
        enable_publishing:   false,
        allow_symbol_change: false,
        withdateranges:      true,
        hide_side_toolbar:   false,
        save_image:          false,
        container_id:        id,
      });
    }

    if (document.querySelector('script[src="https://s3.tradingview.com/tv.js"]')) {
      init();
    } else {
      const script  = document.createElement("script");
      script.src    = "https://s3.tradingview.com/tv.js";
      script.async  = true;
      script.onload = init;
      document.head.appendChild(script);
    }

    return () => {
      const el = document.getElementById(id);
      if (el) el.innerHTML = "";
    };
  }, [ticker, theme]);

  return (
    <div
      style={{ height: 700, position: "relative" }}
      onMouseLeave={() => { setActive(false); setHovered(false); }}
    >
      <div id={idRef.current} style={{ height: "100%" }} />

      {!active && (
        <div
          ref={overlayRef}
          onClick={() => setActive(true)}
          onMouseEnter={() => setHovered(true)}
          onMouseLeave={() => setHovered(false)}
          onWheel={handleWheel}
          style={{
            position: "absolute", inset: 0, zIndex: 1000,
            cursor: "pointer",
            display: "flex", alignItems: "center", justifyContent: "center",
          }}
        >
          <span style={{
            background: "rgba(0,0,0,0.65)",
            color: "#e5e7eb",
            fontSize: 12, fontWeight: 500,
            padding: "6px 18px", borderRadius: 999,
            backdropFilter: "blur(6px)",
            border: "1px solid rgba(255,255,255,0.12)",
            pointerEvents: "none",
            opacity: hovered ? 1 : 0,
            transition: "opacity 0.18s ease",
          }}>
            Click to interact with chart
          </span>
        </div>
      )}

      {active && (
        <div style={{
          position: "absolute", bottom: 12,
          left: "50%", transform: "translateX(-50%)",
          zIndex: 20,
          background: "rgba(0,0,0,0.55)", color: "#9ca3af",
          fontSize: 11, padding: "4px 14px", borderRadius: 999,
          pointerEvents: "none", backdropFilter: "blur(4px)",
          border: "1px solid rgba(255,255,255,0.08)",
          whiteSpace: "nowrap",
        }}>
          Move mouse out of chart to scroll page
        </div>
      )}
    </div>
  );
}
