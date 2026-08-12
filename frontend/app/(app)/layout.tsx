"use client";

import NavBar from "@/components/NavBar";
import MarketTicker from "@/components/MarketTicker";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="h-full flex flex-col">
      <NavBar />
      <MarketTicker />
      <div style={{ flex: 1, minHeight: 0, overflowY: "auto" }}>
        {children}
      </div>
    </div>
  );
}
