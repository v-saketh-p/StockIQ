"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import ARMSignals from "@/components/ARMSignals";
import ARMTracker from "@/components/ARMTracker";

export default function ARMPage() {
  const router  = useRouter();
  const [tab, setTab] = useState<"scanner" | "tracker">("scanner");

  return (
    <div className="p-6 flex flex-col gap-5" style={{ background: "var(--background)", minHeight: "calc(100vh - 96px)" }}>
      <div className="flex gap-1 p-1 rounded-xl self-start"
        style={{ background: "var(--surface2)", border: "1px solid var(--border)" }}>
        {(["scanner", "tracker"] as const).map(t => (
          <button key={t} onClick={() => setTab(t)}
            className="px-4 py-1.5 rounded-lg text-xs font-semibold transition-all"
            style={tab === t
              ? { background: "var(--surface)", color: "var(--text)", boxShadow: "0 1px 3px var(--shadow)" }
              : { color: "var(--muted2)" }}>
            {t === "scanner" ? "Scanner" : "Tracker"}
          </button>
        ))}
      </div>
      {tab === "scanner"
        ? <ARMSignals  onSelectTicker={t => router.push(`/research?ticker=${t}`)} />
        : <ARMTracker  onSelectTicker={t => router.push(`/research?ticker=${t}`)} />
      }
    </div>
  );
}
