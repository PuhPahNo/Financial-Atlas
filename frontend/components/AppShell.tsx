"use client";

import { usePathname } from "next/navigation";
import NavBar from "./NavBar";

// Paper Trading gets a full-bleed canvas (its own vertical sidebar). Every other
// route keeps the global top navbar + the constrained content column.
export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const bare = pathname.startsWith("/paper-trading");

  if (bare) return <>{children}</>;

  return (
    <>
      <NavBar />
      <main className="mx-auto max-w-[1180px] px-4 py-6 sm:px-7 sm:py-7">{children}</main>
      <footer className="mx-auto max-w-[1180px] px-4 py-10 text-xs text-faint sm:px-7">
        Data: SEC EDGAR · Yahoo Finance · FMP · Finnhub. Research tool — not financial advice. Fair values are model outputs.
      </footer>
    </>
  );
}
