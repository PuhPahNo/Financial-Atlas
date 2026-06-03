# 20 — Screener

> Parent: [00-master-prd.md](00-master-prd.md) · Discovery over the locally cached dataset.

## 1. Purpose / why

Let users filter the universe by fundamental, valuation, and technical criteria to surface candidates,
then drill into Overview/Valuation. Runs against our **local normalized dataset** (no per-query
external calls), so it's fast and quota-free.

## 2. User stories & acceptance criteria

- *As a user,* I filter stocks by multiple criteria. **AC:** combine filters (e.g. `FCF Margin > 15%`,
  `P/E < 20`, `Market Cap > $2B`, `MoS > 20%`) and get a ranked, sortable result table.
- *As a user,* I save and reuse screens. **AC:** a filter spec can be saved and re-run.
- *As a user,* I act on results. **AC:** each row links to Overview and can be added to a watchlist
  ([21](21-watchlists.md)).

## 3. Scope (in / out)

- **In:** filter builder over fundamentals/valuation/technical metrics, sortable results, saved
  screens, export, add-to-watchlist.
- **Out:** real-time intraday screening; screening across the *entire* US market beyond the cached
  universe (bounded by what's ingested — see [00 open question](00-master-prd.md#11-open-questions)).

## 4. Data requirements & sources

- Endpoint: `POST /api/v1/screener` with a filter spec → matching tickers + the metrics referenced
  ([04](04-api-contract.md)).
- Source: **local DB only** — `companies`, latest fundamentals, `derived_metrics`, latest
  `valuation_results` ([03](03-data-model.md)). No external calls at query time.

## 5. Contracts

- Request: `{ filters:[{metric, op, value}], sort:{metric,dir}, limit }`. Response:
  `{ results:[{ticker, name, ...requested_metrics}], total }`.
- **Precondition:** metrics/ops are from a known whitelist (prevents arbitrary queries).
  **Postcondition:** results satisfy all filters; metrics shown are as-of the latest cached values
  with an `as_of`.

## 6. UI/UX

- Filter builder (metric dropdown + operator + value, add/remove rows) + results `DataTable`
  (sortable, paginated) + save-screen + add-to-watchlist actions ([06](06-design-system-ui.md)).

## 7. Business logic

- Filters compile to safe parameterized SQL over indexed columns/`derived_metrics`.
- The screenable universe = tickers present in the DB; coverage shown ("screening N companies") so
  users aren't misled about completeness (no silent caps — [Workflow/Pragmatic honesty principle]).

## 8. Dependencies

[03](03-data-model.md), [04](04-api-contract.md), [06](06-design-system-ui.md), [21](21-watchlists.md),
[05](05-caching-and-jobs.md) (universe warmed by jobs).

## 9. Edge cases & error handling

- Metric missing for a company → excluded from that filter (and noted), not treated as 0.
- Empty universe / no matches → clear empty state with the active filter summary.

## 10. Testing requirements

- Filter→SQL compilation tests (incl. whitelist enforcement / injection safety); multi-filter result
  correctness on a seeded DB; coverage-count test.

## 11. Open questions & assumptions

- Universe size depends on ingest scope ([00](00-master-prd.md#11-open-questions)); **assume** start
  with watchlisted + popular tickers, expand via `warm_universe` job.

## 12. Done criteria

- Multi-criteria screening over the local dataset returns ranked results with clear coverage, saved
  screens, and add-to-watchlist.
