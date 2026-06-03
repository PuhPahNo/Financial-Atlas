"use client";

import { useEffect } from "react";
import Link from "next/link";
import { useParams, usePathname } from "next/navigation";
import { recordRecent } from "@/lib/recents";

const TABS = [
  { label: "Overview", path: "" },
  { label: "Charts", path: "/charts" },
  { label: "Financials", path: "/financials" },
  { label: "Cash Flow", path: "/cash-flow" },
  { label: "Valuation", path: "/valuation" },
  { label: "Ownership", path: "/ownership" },
  { label: "Filings", path: "/filings" },
];

export default function CompanyLayout({ children }: { children: React.ReactNode }) {
  const params = useParams();
  const pathname = usePathname();
  const ticker = String(params.ticker || "").toUpperCase();
  const base = `/company/${ticker}`;
  useEffect(() => {
    if (ticker) recordRecent(ticker);
  }, [ticker]);

  return (
    <div>
      <nav className="mb-7 flex gap-7 border-b border-line">
        {TABS.map((t) => {
          const href = `${base}${t.path}`;
          const active = pathname === href || (t.path === "" && pathname === base);
          return (
            <Link
              key={t.label}
              href={href}
              className={`-mb-px border-b-2 pb-3 text-sm transition-colors ${
                active ? "border-accent text-text" : "border-transparent text-muted hover:text-text"
              }`}
            >
              {t.label}
            </Link>
          );
        })}
      </nav>
      {children}
    </div>
  );
}
