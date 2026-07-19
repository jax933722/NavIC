import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "NavIC — Opportunity Intelligence",
  description: "Evidence-backed opportunities from public buying signals.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <nav
          style={{
            display: "flex",
            gap: 16,
            padding: "12px 24px",
            borderBottom: "1px solid var(--border)",
          }}
        >
          <a href="/">Opportunities</a>
          <a href="/search">Search</a>
          <a href="/graph">Graph</a>
          <a href="/collectors">Collectors</a>
          <a href="/review">Review</a>
        </nav>
        {children}
      </body>
    </html>
  );
}
