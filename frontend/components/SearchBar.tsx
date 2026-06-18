"use client";

import { useState } from "react";
import { Search } from "lucide-react";

export default function SearchBar({ onSearch }: { onSearch: (ticker: string) => void }) {
  const [value, setValue] = useState("");

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const t = value.trim().toUpperCase();
    if (t) { onSearch(t); setValue(""); }
  }

  return (
    <form onSubmit={handleSubmit} className="flex items-center gap-2 flex-1 max-w-sm">
      <div
        className="flex items-center gap-2 flex-1 rounded-lg px-3 py-2 border"
        style={{ background: "var(--surface2)", borderColor: "var(--border)" }}
      >
        <Search size={14} style={{ color: "var(--muted)" }} />
        <input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="Search ticker…  e.g. TSLA"
          className="flex-1 bg-transparent outline-none text-sm"
          style={{ color: "var(--text)" }}
          autoComplete="off"
          spellCheck={false}
        />
      </div>
      <button
        type="submit"
        className="px-4 py-2 rounded-lg text-sm font-semibold transition-opacity hover:opacity-80"
        style={{ background: "var(--blue)", color: "#fff" }}
      >
        Go
      </button>
    </form>
  );
}
