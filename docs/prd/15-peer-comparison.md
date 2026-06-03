# 15 — Peer Comparison

> Parent: [00-master-prd.md](00-master-prd.md) · May merge into [14](14-valuation-engine.md) if it
> stays small (per [plan open assumptions](00-master-prd.md)).

## 1. Purpose / why

Put a company in context against comparable peers and derive relative-valuation fair values from
peer-median multiples — a sanity check on the absolute models in [14](14-valuation-engine.md).

## 2. User stories & acceptance criteria

- *As a user,* I see a peer set with side-by-side multiples. **AC:** a table of peers with P/E, Fwd
  P/E, EV/Sales, EV/EBITDA, Price/FCF, PEG, plus the median row.
- *As a user,* I get implied fair values from peer medians. **AC:** `EPS×medianPE`, `Rev×medianEV/Sales`,
  `EBITDA×medianEV/EBITDA` → equity → per share, feeding the Peer Comps model in [14](14-valuation-engine.md).
- *As a user,* I can adjust the peer set. **AC:** add/remove tickers; medians recompute.

## 3. Scope (in / out)

- **In:** peer-set selection (default + manual), multiple table, peer medians, implied values, sector
  context.
- **Out:** the blended valuation math ([14](14-valuation-engine.md)).

## 4. Data requirements & sources

- Endpoint: `GET /api/v1/peers/{ticker}` → `{ peers:[{ticker,...multiples}], medians:{...} }`
  ([04](04-api-contract.md)).
- Default peer set: same SIC/industry from `companies` ([03](03-data-model.md)); multiples computed
  from each peer's cached fundamentals + price. Manual overrides accepted.

## 5. Contracts

- **Precondition:** ≥3 peers with valid metrics for a meaningful median (else flag "insufficient
  peers"). **Postcondition:** medians ignore `null`/negative-where-meaningless multiples (e.g. negative
  P/E excluded), and the exclusion is reported.

## 6. UI/UX

- `DataTable` of peers + a highlighted subject row + a median row; implied fair values shown and linked
  into `ValuationSummary` ([06](06-design-system-ui.md)). Editable peer chips.

## 7. Business logic

- Implied EV-based values: `metric × peer_median → EV → −NetDebt → /shares` (Glossary).
- Outlier handling: optionally winsorize/median (median is default — robust to outliers).

## 8. Dependencies

[14](14-valuation-engine.md), [03](03-data-model.md), [04](04-api-contract.md), [06](06-design-system-ui.md),
[10](10-company-overview.md) (metrics).

## 9. Edge cases & error handling

- Sparse industry / unique company → "insufficient comparable peers"; peer-comps weight drops to 0 in
  the blend ([14 §6](14-valuation-engine.md)).
- Mixed-currency peers → normalize or flag; **assume** US peers in USD for v1.

## 10. Testing requirements

- Median computation excludes negatives/nulls correctly; implied-value math vs hand-computed; manual
  peer override recomputes medians.

## 11. Open questions & assumptions

- Default peer-selection heuristic: **assume** same industry + nearest market-cap band; refine later.

## 12. Done criteria

- Default peer set + editable overrides render with multiples + medians and feed implied values into
  the valuation blend.
