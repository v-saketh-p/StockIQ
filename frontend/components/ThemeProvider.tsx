"use client";

import { createContext, useContext, useEffect, useState } from "react";

export type Theme = "dark" | "light" | "vintage" | "finance";

export const THEMES: { id: Theme; label: string; bg: string; surface: string; text: string }[] = [
  { id: "dark",    label: "Dark",          bg: "#000000", surface: "#0a0a0a", text: "#e8e8e8" },
  { id: "finance", label: "Finance Pro",   bg: "#0a0f1e", surface: "#111827", text: "#f1f5f9" },
  { id: "light",   label: "Light",         bg: "#fafafa", surface: "#ffffff", text: "#09090b" },
  { id: "vintage", label: "Vintage Paper", bg: "#f5f0e8", surface: "#faf7f0", text: "#2c2416" },
];

const ThemeContext = createContext<{ theme: Theme; setTheme: (t: Theme) => void }>({
  theme: "dark",
  setTheme: () => {},
});

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<Theme>("dark");

  useEffect(() => {
    const raw = localStorage.getItem("theme");
    const saved: Theme = (raw === "dark" || raw === "light" || raw === "vintage" || raw === "finance") ? raw : "dark";
    setThemeState(saved);
    document.documentElement.setAttribute("data-theme", saved);
  }, []);

  function setTheme(t: Theme) {
    setThemeState(t);
    localStorage.setItem("theme", t);
    document.documentElement.setAttribute("data-theme", t);
  }

  return (
    <ThemeContext.Provider value={{ theme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  return useContext(ThemeContext);
}
