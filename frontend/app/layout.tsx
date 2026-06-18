import type { Metadata } from "next";
import "./globals.css";
import NavBar from "@/components/NavBar";
import { ThemeProvider } from "@/components/ThemeProvider";

export const metadata: Metadata = {
  title: "StockIQ — Research Dashboard",
  description: "Professional stock analysis tool",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="h-full" suppressHydrationWarning>
      {/* Inline script runs before React hydration to prevent flash of wrong theme */}
      <head>
        <script dangerouslySetInnerHTML={{ __html: `
          try {
            var t = localStorage.getItem('theme') || 'dark';
            document.documentElement.setAttribute('data-theme', t);
          } catch(e) {}
        `}} />
      </head>
      <body className="h-full flex flex-col" style={{ background: "var(--background)" }}>
        <ThemeProvider>
          <NavBar />
          <div style={{ flex: 1, minHeight: 0, overflowY: "auto" }}>
            {children}
          </div>
        </ThemeProvider>
      </body>
    </html>
  );
}
