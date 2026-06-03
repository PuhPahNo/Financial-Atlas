"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import SearchBar from "./SearchBar";

const LINKS = [
  { label: "Dashboard", href: "/" },
  { label: "Screener", href: "/screener" },
  { label: "Watchlists", href: "/watchlists" },
  { label: "Paper Trading", href: "/paper-trading" },
];

export default function NavBar() {
  const pathname = usePathname();
  const isHome = pathname === "/";

  return (
    <header className="sticky top-0 z-40 border-b border-line bg-bg/80 backdrop-blur-xl">
      <div className="mx-auto flex max-w-[1180px] items-center gap-5 px-7 py-3.5">
        <Link href="/" className="flex shrink-0 items-center gap-2.5 font-semibold tracking-tight">
          <span className="grid h-7 w-7 place-items-center rounded-lg bg-gradient-to-br from-accent to-positive shadow-glow">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden>
              <path d="M2 10.5 L5.5 6 L8 8.5 L12 3" stroke="#0a0a0f" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </span>
          Atlas
        </Link>

        {/* Global search — hidden on the dashboard, which has the hero search (no duplicate). */}
        {!isHome && <div className="hidden min-w-0 flex-1 md:block"><div className="max-w-sm"><SearchBar /></div></div>}

        <nav className="ml-auto flex items-center gap-1 text-sm">
          {LINKS.map((l) => {
            const active = l.href === "/" ? isHome : pathname.startsWith(l.href);
            return (
              <Link key={l.href} href={l.href} className={`rounded-lg px-3 py-1.5 transition-colors ${active ? "bg-surface-2 text-text" : "text-muted hover:text-text"}`}>
                {l.label}
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
