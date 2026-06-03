# 21 — Watchlists

> Parent: [00-master-prd.md](00-master-prd.md) · Persistent lists tying price to fair value.

## 1. Purpose / why

Let users track a set of tickers with the metrics that matter for a value investor — current price,
blended fair value, upside/downside, and margin of safety — refreshed in the background so the list
is always current.

## 2. User stories & acceptance criteria

- *As a user,* I maintain named watchlists. **AC:** create/rename/delete lists; add/remove tickers.
- *As a user,* each row shows price vs fair value. **AC:** columns for current price, blended fair
  value, upside/downside %, MoS, last-updated.
- *As a user,* watchlisted tickers stay fresh. **AC:** background jobs refresh their data/valuations
  ([05](05-caching-and-jobs.md)).

## 3. Scope (in / out)

- **In:** watchlist CRUD, item CRUD, computed columns (upside/MoS), sort, link to Overview/Valuation,
  background refresh.
- **Out:** alerts/notifications (post-v1); sharing (depends on accounts — [30](30-deployment-render.md)).

## 4. Data requirements & sources

- Endpoints: `GET/POST/PUT/DELETE /api/v1/watchlists` and items ([04](04-api-contract.md)).
- Source: `watchlists` / `watchlist_items` + latest `valuation_results` + price ([03](03-data-model.md)).
- `recompute_valuations` + `refresh_prices` keep watchlisted tickers warm ([05](05-caching-and-jobs.md)).

## 5. Contracts

- Response: `{ watchlists:[{id,name,items:[{ticker, price, blended_fair_value, upside_pct, mos,
  last_updated}]}] }`.
- **Precondition:** valid watchlist id for item ops; ticker resolvable on add. **Postcondition:**
  computed columns derive from the latest stored valuation + price; `last_updated` reflects data
  freshness (not row creation).

## 6. UI/UX

- List selector + `DataTable` of items with computed columns (green/red upside), reusing
  `ValuationSummary` semantics; add-ticker input; row → Overview/Valuation ([06](06-design-system-ui.md)).

## 7. Business logic

- `upside_pct = (fair_value − price)/price`; `mos` per Glossary. Adding a ticker triggers a one-off
  fetch + default valuation if not already cached.

## 8. Dependencies

[03](03-data-model.md), [04](04-api-contract.md), [05](05-caching-and-jobs.md), [06](06-design-system-ui.md),
[14](14-valuation-engine.md), [20](20-screener.md) (add-from-screener).

## 9. Edge cases & error handling

- Ticker with no valuation yet → show price + "valuation pending" until the job computes it.
- Deleting a list → confirm; cascade-delete items.
- Duplicate ticker in a list → prevented by unique constraint ([03](03-data-model.md)).

## 10. Testing requirements

- CRUD integration tests; computed-column math tests; "valuation pending" state test; refresh-job
  updates `last_updated`.

## 11. Open questions & assumptions

- Single-tenant (`user_id='local'`) until accounts decided in [30](30-deployment-render.md).

## 12. Done criteria

- Named watchlists with add/remove, computed price-vs-fair-value columns, background freshness, and
  links into Overview/Valuation.
