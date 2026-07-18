import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "NavIC — Opportunity Intelligence",
  description: "Evidence-backed opportunities from public buying signals.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
