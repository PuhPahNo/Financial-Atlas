import type { Metadata } from "next";
import { Inter, Fraunces, IBM_Plex_Mono } from "next/font/google";
import "./globals.css";
import AppShell from "@/components/AppShell";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });
const fraunces = Fraunces({ subsets: ["latin"], weight: ["500", "600"], variable: "--font-fraunces", display: "swap" });
const mono = IBM_Plex_Mono({ subsets: ["latin"], weight: ["400", "500", "600"], variable: "--font-mono", display: "swap" });

export const metadata: Metadata = {
  title: "Atlas",
  description: "High-end stock analysis & valuation on free public data",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${fraunces.variable} ${mono.variable}`}>
      <body className="min-h-screen bg-bg font-sans text-text antialiased">
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
