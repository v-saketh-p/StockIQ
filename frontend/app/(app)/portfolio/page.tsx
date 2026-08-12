"use client";

import { useRouter } from "next/navigation";
import PortfolioTracker from "@/components/PortfolioTracker";

export default function PortfolioPage() {
  const router = useRouter();
  return (
    <div className="p-6" style={{ background: "var(--background)", minHeight: "calc(100vh - 96px)" }}>
      <PortfolioTracker onSelectTicker={t => router.push(`/research?ticker=${t}`)} />
    </div>
  );
}
