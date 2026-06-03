"use client";

import { Category } from "@/lib/paperTradingApi";

export default function CategoryTabs({
  categories,
  active,
  onChange,
}: {
  categories: Category[];
  active: string;
  onChange: (id: string) => void;
}) {
  return (
    <div className="flex gap-2 overflow-x-auto rounded-xl border border-line bg-surface/40 p-2" role="tablist" aria-label="Trading bot categories">
      {categories.map((category) => (
        <button
          key={category.id}
          role="tab"
          aria-selected={active === category.id}
          onClick={() => onChange(category.id)}
          className={`min-w-fit rounded-lg px-4 py-2 text-left text-sm transition-colors ${
            active === category.id ? "bg-accent text-white shadow-glow" : "text-muted hover:bg-surface-2 hover:text-text"
          }`}
        >
          <span className="block font-medium">{category.label}</span>
          <span className="block text-[11px] opacity-80">{category.strategies.length} models</span>
        </button>
      ))}
    </div>
  );
}
