# 10 — Company Overview

> Parent: [00-master-prd.md](00-master-prd.md) · The landing page for a ticker and the Phase 2 tracer
> bullet target.

## 1. Purpose / why

Give an at-a-glance company snapshot — identity, price, key valuation/quality metrics — that orients
the analyst and links into every deeper module. This is the first page proven end-to-end (tracer
bullet).

## 2. User stories & acceptance criteria

- *As a user,* I search a ticker and land on a profile with current price and headline metrics. **AC:**
  `/company/[ticker]` renders name, sector/industry, price, and the metric grid from real data.
- *As a user,* I can jump to Financials/Valuation/Insiders from here. **AC:** left-rail links route to
  the right modules for the same ticker.
- *As a user,* I can see how fresh the data is and where it came from. **AC:** `SourceBadge` shows
  `served_by`/`stale` from `meta`.

## 3. Scope (in / out)

- **In:** profile header, key-metrics grid, mini price sparkline, quick links, a compact valuation
  teaser (current vs blended fair value).
- **Out:** full charts ([11](11-price-volume-charts.md)), full statements ([12](12-financial-statements.md)),
  full valuation ([14](14-valuation-engine.md)).

## 4. Data requirements & sources

- Endpoint: `GET /api/v1/company/{ticker}` ([04](04-api-contract.md)).
- Profile from EDGAR (CIK/SIC) → FMP/Finnhub fallback; price from price chain; metrics computed from
  latest fundamentals + price ([02 fallback chains](02-data-sources.md)).

## 5. Contracts

`CompanyProfile` response: identity fields + `key_metrics` object:
`market_cap, price, change_abs, change_pct, week52_high, week52_low, pe, price_to_fcf, ev_ebitda,
dividend_yield (nullable), shares_outstanding`.
- **Precondition:** ticker resolvable. **Postcondition:** every metric present or explicit `null`
  (never 0-as-missing); `meta` populated. Metric definitions per [Glossary](00-master-prd.md#7-glossary).

## 6. UI/UX

- Header: name, ticker, exchange, sector/industry, current price + change (colored), 52-wk range bar.
- `MetricCard` grid: P/E, Price/FCF, EV/EBITDA, Dividend Yield, Market Cap, Shares Out.
- Compact `ValuationSummary` teaser (current vs blended fair value + MoS) linking to [14](14-valuation-engine.md).
- Small price sparkline (reuses `TrendChart`); company description (expandable).
- Reuses `MetricCard`, `ValuationSummary`, `SourceBadge`, `StateView` ([06](06-design-system-ui.md)).

## 7. Business logic

- Derived metrics (Price/FCF, EV/EBITDA, dividend yield) computed per Glossary; nulls when inputs
  missing (e.g. no dividend → yield `null`, not `0`).

## 8. Dependencies

[04](04-api-contract.md), [02](02-data-sources.md), [03](03-data-model.md), [06](06-design-system-ui.md),
[14](14-valuation-engine.md) (teaser).

## 9. Edge cases & error handling

- Pre-revenue/negative-earnings company → P/E `null` with tooltip "N/M"; ADRs/foreign currency labeled.
- No valuation yet computed → teaser shows "Run valuation" CTA instead of numbers.

## 10. Testing requirements

- API contract test for `/company/{ticker}`; component test for the metric grid with null metrics;
  e2e: search → overview renders for a known ticker (tracer-bullet test).

## 11. Open questions & assumptions

- Quote freshness on overview: **assume** EOD/delayed is fine for v1 (free tiers); real-time deferred.

## 12. Done criteria

- **Tracer bullet (Phase 2):** search a ticker → overview renders identity + price + metric grid from
  live, cached data end-to-end. → Thicken with valuation teaser + sparkline.
