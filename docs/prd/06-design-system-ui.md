# 06 — Design System & UI Conventions

> Parent: [00-master-prd.md](00-master-prd.md) · Shared UI vocabulary so feature pages look and
> behave consistently and reuse components (DRY).

## 1. Purpose / why

Define the layout shell, theming, reusable component library, charting conventions, formatting, and
accessibility rules once — so every feature page (10–21) composes existing primitives instead of
reinventing them.

## 2. User stories & acceptance criteria

- *As a user,* every page shares one navigation/search shell and consistent number formatting. **AC:**
  ticker search + global nav present on all pages; `$1.23B`, `12.3%`, `(1.2)` negatives uniform.
- *As a dev,* I build a new page from existing components. **AC:** new feature pages introduce no
  duplicate table/card/chart primitives.
- *As a user,* the app is readable in light/dark and on a laptop screen. **AC:** dark default, light
  toggle; responsive ≥ 1024px, graceful ≥ 768px.

## 3. Scope (in / out)

- **In:** app shell, theme tokens, component catalog, chart conventions, formatters, loading/empty/
  error states, accessibility.
- **Out:** per-feature content (feature PRDs), API shapes ([04](04-api-contract.md)).

## 4. App shell & navigation

```txt
┌ Top bar: logo · global ticker search (typeahead → /search) · theme toggle ─┐
│ Left rail (per company): Overview · Charts · Financials · Cash Flow ·       │
│   Valuation · Insiders · Institutions · Filings · News                      │
│ Global: Screener · Watchlists · Paper Trading                               │
└ Content area: page composes cards/tables/charts ───────────────────────────┘
```

Routes per [01](01-architecture.md): `/company/[ticker]`, `/financials/[ticker]/*`,
`/valuation/[ticker]`, `/screener`, `/watchlists`, `/paper-trading`.

## 5. Theme tokens

- Tailwind config holds the only source of color/spacing/typography tokens (DRY).
- Dark default. Semantic colors: `positive` (green), `negative` (red), `neutral`, `accent`, `muted`.
- Financial color rule: gains green, losses red, applied via one helper — never ad-hoc.

## 6. Component catalog (reused everywhere)

| Component | Role | Used by |
| --- | --- | --- |
| `MetricCard` | one labeled metric + delta + tooltip(source) | Overview, Valuation, Cash Flow |
| `FinancialTable` | period-columned table, sticky header, raw/derived badge | Financials, Cash Flow, Ownership |
| `TrendChart` | line/area for a metric over periods | Cash Flow, Financials trends |
| `StockChart` | candlestick (TradingView Lightweight Charts) | Charts |
| `VolumeChart` | volume bars synced to StockChart | Charts |
| `ValuationSummary` | current vs fair-value range + MoS | Valuation, Watchlists |
| `FairValueRange` | bear/base/bull/blended visualization | Valuation |
| `ScenarioInputs` | editable assumption form | Valuation |
| `DataTable` | generic sortable/filterable table | Screener, Insiders, Institutions, Filings |
| `SourceBadge` | shows `served_by` + stale indicator from `meta` | all data views |
| `StateView` | standardized loading / empty / error / stale | all |
| `StrategyCard` | paper model profile + caveats + headline metrics | Paper Trading |
| `BacktestChart` | equity/drawdown/benchmark visualization | Paper Trading |

## 7. Charting conventions

- **Price/volume:** TradingView Lightweight Charts (per stack decision). Candlesticks + synced volume;
  timeframe toggle maps to `range`/`interval` ([04](04-api-contract.md)).
- **Metric trends:** a single `TrendChart` (lightweight SVG/canvas lib) for FCF/margins/etc., so all
  trend visuals share one component and tooltip style.
- Every chart labels units, handles missing periods (gaps, not zeros), and shows a `SourceBadge`.

## 8. Formatting (single source)

`lib/formatters.ts` is the only place numbers/dates/currency are formatted:
- Large money → `$1.23B / $456.7M / $12.3K`; percentages → one decimal; negatives in parentheses for
  financial tables; share counts abbreviated; `null` → `—` (never `0` or blank that implies a value).

## 9. States: loading / empty / error / stale

- `StateView` standardizes all four. **Stale** (from `meta.stale`) shows a subtle banner: "Showing
  cached data from {as_of}". **Empty** distinguishes "no data exists" from "not yet loaded".

## 10. Accessibility & performance

- Keyboard-navigable search and tables; ARIA labels on charts (text summary alternative).
- Color is never the *only* signal (icons/sign accompany green/red).
- Code-split heavy chart libs; memoize tables; target interaction-ready < 2 s on warm data.

## 11. Dependencies

[04](04-api-contract.md) (consumes `meta`), all feature PRDs (compose these components).

## 12. Edge cases · Testing · Done

- **Edge cases:** ultra-long company names truncate with tooltip; tables with one period still render;
  RTL/locale deferred (US v1).
- **Testing:** component tests (RTL) for `MetricCard`/`FinancialTable`/`StateView` incl. null/stale;
  visual smoke via Playwright on Overview.
- **Done criteria:** tracer bullet = app shell + search + `MetricCard` + `StateView` render the
  Overview page. → Thicken as feature pages adopt the catalog.
