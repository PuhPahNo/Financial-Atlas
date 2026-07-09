# 00 — Master PRD: Financial Atlas

> **Status:** Draft v1 · **Owner:** Project maintainer · **Phase:** 1 (documentation)
> This is the root document. Every other PRD links back here for shared vocabulary, scope, and
> phase context. Definitions live **only** in the [Glossary](#7-glossary) — other PRDs reference
> them, never redefine (DRY).

---

## 1. Vision

Build **Financial Atlas** — a high-end, local-first equity research and valuation platform in the
class of Koyfin / Finviz / AlphaSense — that turns **free public data** (SEC filings, financial
statements, price & volume, insider trading, institutional ownership) into clean charts,
transparent valuation models, and defensible fair-value ranges.

The platform should feel like a serious analyst's cockpit: fast, modular, and honest about its
assumptions. It is a **research tool, not financial advice** — every fair value is a labeled model
output, never a recommendation.

## 2. Why this exists

- Professional terminals (Bloomberg, Koyfin Pro, AlphaSense) are expensive and closed.
- The raw data needed for rigorous analysis is **largely free** — SEC EDGAR alone provides filings,
  XBRL financials, insider trades (Form 4), and institutional holdings (13F). The gap is **tooling**,
  not data.
- Existing free tools silo the pieces (Finviz screens, EDGAR filings, a spreadsheet for DCF).
  Financial Atlas unifies them and adds **multi-model valuation** with editable assumptions.

## 3. Personas

| Persona | Needs | Primary modules |
| --- | --- | --- |
| **The DIY value investor** (primary) | Statement trends, FCF quality, intrinsic value with margin of safety | Financials, Cash Flow Analysis, Valuation |
| **The screener-first hunter** | Filter the universe by fundamentals/valuation, then drill in | Screener, Watchlists, Overview |
| **The filings analyst** | Read 8-Ks, track insider clusters and institutional moves | SEC Filings, Insider Trading, Institutional Ownership |
| **The maintainer** (us) | Add data sources & models without breaking others | Architecture, Data Sources, Testing |

## 4. Scope

### In scope (this product)
- US-listed public companies (initially). Profile, price/volume, full financial statements.
- Dedicated **Cash Flow Analysis** module (FCF trends, margins, conversion, capital returns).
- **Multi-model valuation engine** with bull/base/bear scenarios and a blended fair value.
- **Insider trading** (Form 4) and **institutional ownership** (13F / 13D/G).
- **SEC filings explorer** with full-text search and an 8-K event timeline.
- **Screener** and **watchlists** over the locally cached dataset.
- News, earnings/dividend calendars, and macro context (FRED).
- Simulated **paper trading** and backtesting over free public data, with no real order execution.
- A research assistant that can query Atlas data and run confirmed local paper-trading actions.

### Out of scope
- Real-time tick data, intraday level-2, deep options flow (not feasible on free tiers — see
  [02 §Premium Upgrade Appendix](02-data-sources.md)).
- Brokerage integration, order execution, moving money — **permanently out of scope**.
- Non-US markets in v1 (revisit after the US build is stable).
- Anything presented as personalized financial advice.
- Execution-grade backtests that imply intraday fills, real options-chain pricing, or live trading.

## 5. Success metrics

- **Coverage:** for any US large/mid-cap ticker, Overview + Financials + Cash Flow + Valuation
  render with real data in < 3 s warm / < 10 s cold.
- **Correctness:** valuation functions match hand-computed reference values in unit tests (±0.5%).
- **Resilience:** no single data provider outage breaks a page (fallback chain proven by tests).
- **Maintainability:** a new data provider or valuation model can be added by implementing one
  interface, with no edits to UI or unrelated modules (orthogonality).

## 6. Architecture at a glance

Monorepo: Next.js/TypeScript frontend ↔ FastAPI/Python backend ↔ pluggable data providers ↔
local cache + SQLite (→ Postgres on Render). Full detail in [01-architecture.md](01-architecture.md).

```txt
[Next.js UI] → [FastAPI REST API] → [Service layer] → [Provider adapters] → [Free data sources]
                                          │
                                   [Cache] + [SQLite/Postgres] + [Background refresh jobs]
```

## 7. Glossary

> **Canonical definitions. Reference these from other PRDs; do not duplicate.**

- **FCF (Free Cash Flow):** `Operating Cash Flow − Capital Expenditures`. Capex is reported as a
  negative cash outflow; FCF uses its absolute magnitude consistently.
- **FCF Margin %:** `FCF / Revenue`.
- **FCF Conversion %:** `FCF / Net Income` (how much accounting profit becomes cash).
- **FCF per Share:** `FCF / Diluted Weighted-Average Shares Outstanding`.
- **CapEx as % of Revenue:** `|CapEx| / Revenue`.
- **Owner Earnings:** `Net Income + D&A − Maintenance CapEx ± ΔWorking Capital` (Buffett definition).
- **Net Debt:** `Total Debt − Cash & Equivalents` (and short-term investments where reported).
- **Enterprise Value (EV):** `Market Cap + Net Debt` (minority interest/preferred added when present).
- **Margin of Safety (MoS):** `(Fair Value − Current Price) / Fair Value`.
- **Blended Fair Value:** weighted average of per-model fair values (default weights in
  [14-valuation-engine.md](14-valuation-engine.md); adjustable).
- **Scenario (Bear/Base/Bull):** a named set of assumption overrides applied across models.
- **Provider:** an adapter implementing the data-provider interface for one external source
  ([02-data-sources.md](02-data-sources.md)).
- **Fiscal period:** `{fiscal_year, period}` where `period ∈ {FY, Q1, Q2, Q3, Q4}`.
- **Raw vs Derived:** *raw* = values as reported by a source; *derived* = values we compute. They
  are stored separately ([03-data-model.md](03-data-model.md)).
- **Paper strategy:** a saved, parameterized research model that emits simulated trading signals.
- **Trader account:** a local simulated profile that allocates starting capital across one or more
  strategies and replays those sleeves over real historical prices.
- **Backtest:** a deterministic historical simulation using documented data and fill assumptions.

## 8. PRD index

| # | File | Module |
| --- | --- | --- |
| 00 | [00-master-prd.md](00-master-prd.md) | This document |
| 01 | [01-architecture.md](01-architecture.md) | System architecture |
| 02 | [02-data-sources.md](02-data-sources.md) | Data sources & provider interface |
| 03 | [03-data-model.md](03-data-model.md) | Database schema & migrations |
| 04 | [04-api-contract.md](04-api-contract.md) | REST API contract |
| 05 | [05-caching-and-jobs.md](05-caching-and-jobs.md) | Caching & background jobs |
| 06 | [06-design-system-ui.md](06-design-system-ui.md) | Design system & UI conventions |
| 07 | [07-testing-and-quality.md](07-testing-and-quality.md) | Testing & quality strategy |
| 10 | [10-company-overview.md](10-company-overview.md) | Company overview page |
| 11 | [11-price-volume-charts.md](11-price-volume-charts.md) | Price & volume charts |
| 12 | [12-financial-statements.md](12-financial-statements.md) | Financial statement pages |
| 13 | [13-cash-flow-analysis.md](13-cash-flow-analysis.md) | Cash flow analysis module |
| 14 | [14-valuation-engine.md](14-valuation-engine.md) | Valuation engine |
| 15 | [15-peer-comparison.md](15-peer-comparison.md) | Peer comparison |
| 16 | [16-insider-trading.md](16-insider-trading.md) | Insider trading (Form 4) |
| 17 | [17-institutional-ownership.md](17-institutional-ownership.md) | Institutional ownership (13F) |
| 18 | [18-sec-filings-explorer.md](18-sec-filings-explorer.md) | SEC filings explorer |
| 19 | [19-news-events-macro.md](19-news-events-macro.md) | News, events & macro |
| 20 | [20-screener.md](20-screener.md) | Screener |
| 21 | [21-watchlists.md](21-watchlists.md) | Watchlists |
| 22 | [22-paper-trading.md](22-paper-trading.md) | Paper trading |
| 23 | [23-backtesting-engine.md](23-backtesting-engine.md) | Backtesting engine |
| 24 | [24-research-assistant.md](24-research-assistant.md) | Research assistant |
| 30 | [30-deployment-render.md](30-deployment-render.md) | Deployment to Render |

## 9. Phase map (execution)

| Phase | PRDs implemented | Outcome |
| --- | --- | --- |
| 1 | *(all, as docs)* | This `docs/prd/` set authored & reviewed |
| 2 | 01,02,03,04,05,07,10 | Foundation + tracer bullet (ticker → live overview) |
| 3 | 06,11,12,13 | Charts, statements, cash flow analysis |
| 4 | 14,15 | Valuation engine + peer comps |
| 5 | 16,17,18,19 | Ownership, filings, news/macro |
| 6 | 20,21 | Screener + watchlists |
| 7 | 30 | Hosted on Render (Postgres, jobs, deploy) |
| 8 | 22,23,24 | Paper trading, backtesting, research assistant |

## 10. Guiding principles (Pragmatic Programmer)

- **DRY** — one authoritative definition per concept (this glossary; shared utilities in code).
- **Orthogonality** — providers, models, and UI modules are independent and swappable.
- **Tracer bullets** — every feature ships a thin end-to-end slice first, then thickens.
- **Design by Contract** — APIs and valuation functions state preconditions/postconditions/invariants.
- **Reversibility** — no single data source or library is load-bearing; adapters keep choices cheap.
- **Assertive programming** — never trust external data; validate and normalize at the boundary.
- **Honesty** — show ranges, label assumptions, never imply false precision.

## 11. Open questions

- Confirm initial ticker universe scope (S&P 1500? all US-listed?) — affects bulk-refresh cost.
- Whether to support user accounts in the hosted phase or keep single-tenant — see [30](30-deployment-render.md).
