"use client";

import { useEffect, useRef, useState } from "react";
import { Search } from "lucide-react";

export default function SearchBar({ onSearch }: { onSearch: (ticker: string) => void }) {
  const [value, setValue] = useState("");
  const [focused, setFocused] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    function handler(e: KeyboardEvent) {
      if (e.key !== "/") return;
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "INPUT" || tag === "TEXTAREA") return;
      e.preventDefault();
      inputRef.current?.focus();
    }
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const t = value.trim().toUpperCase();
    if (t) { onSearch(t); setValue(""); }
  }

  return (
    <form onSubmit={handleSubmit} className="flex items-center gap-2 flex-1 max-w-sm">
      <div
        className="flex items-center gap-2 flex-1 rounded-lg px-3 py-2 border transition-colors"
        style={{
          background: "var(--surface2)",
          borderColor: focused ? "var(--blue)" : "var(--border)",
        }}
      >
        <Search size={14} style={{ color: "var(--muted)" }} />
        <input
          ref={inputRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          placeholder="Search ticker…  e.g. TSLA"
          className="flex-1 bg-transparent outline-none text-sm"
          style={{ color: "var(--text)" }}
          autoComplete="off"
          spellCheck={false}
        />
        {!focused && !value && (
          <kbd
            className="hidden sm:inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold flex-shrink-0"
            style={{
              background: "var(--surface3)",
              border: "1px solid var(--border2)",
              color: "var(--muted)",
            }}
          >
            /
          </kbd>
        )}
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
