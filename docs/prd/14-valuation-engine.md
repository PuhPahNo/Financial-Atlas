# 14 — Valuation Engine

> Parent: [00-master-prd.md](00-master-prd.md) · The analytical core. Pure, deterministic, deeply
> tested. Metric definitions per [Glossary](00-master-prd.md#7-glossary).

## 1. Purpose / why

Produce multiple independent fair-value estimates (never one "true" number), combine them into a
transparent blended fair value with bull/base/bear scenarios and a margin of safety, and let users
edit every assumption. Honesty over false precision.

## 2. User stories & acceptance criteria

- *As a user,* I get fair values from several models, not one. **AC:** DCF, Owner Earnings, Earnings
  Multiple, Revenue Multiple, EBITDA Multiple, DDM (if dividend payer), and Peer Comps each produce a
  value with shown inputs/intermediates.
- *As a user,* I see bear/base/bull and a blended value + MoS. **AC:** three scenarios + blended FV +
  MoS render; weights and assumptions are editable and recompute live.
- *As a user,* I can trust and reproduce a result. **AC:** every result stores `assumptions_json` +
  `weights_json` ([03](03-data-model.md)); unit tests match hand-computed values within ±0.5%.

## 3. Scope (in / out)

- **In:** the seven models below, scenario engine, blended FV, MoS, editable assumptions, valuation
  history.
- **Out:** peer-set construction details ([15](15-peer-comparison.md)); data fetching (services).

## 4. Models (pure functions — formulas from the original spec)

Each function: typed inputs → `{ fair_value_per_share, assumptions, intermediates }`.

1. **Discounted Cash Flow** — project FCF (yrs 1–5, 6–10), discount, terminal value, EV→equity→/shares.
   `Terminal Value = FinalFCF·(1+g)/(r−g)`; `Equity = EV − NetDebt`.
2. **Owner Earnings** — `NetIncome + D&A − MaintenanceCapEx ± ΔWC`, then discount like DCF. Maintenance
   capex estimated via (a) avg capex % revenue, (b) D&A proxy, or (c) user % of total capex (selectable).
3. **Earnings Multiple** — `FutureEPS = EPS·(1+g)^n`; `FuturePrice = FutureEPS·FairPE`; discount back.
4. **Revenue Multiple** — `FutureRev·FairEV/Sales → EV → −NetDebt → /shares`, discounted.
5. **EBITDA Multiple** — `FutureEBITDA·FairEV/EBITDA → EV → −NetDebt → /shares`, discounted.
6. **Dividend Discount (Gordon)** — `FairValue = NextDiv/(r−g)`; only when payer and `r > g`.
7. **Peer Comparable** — company metric × peer-median multiple ([15](15-peer-comparison.md)).

## 5. Contracts (Design by Contract)

- **Preconditions (engine-wide):** `discount_rate > terminal_growth_rate` (else error, no
  divide-by-near-zero); shares > 0; required inputs per model present.
- **Postconditions:** each model returns a finite `fair_value_per_share` ≥ 0 **or** an explicit
  `not_applicable` with reason (e.g. DDM for a non-payer, EBITDA model for a bank).
- **Invariants:** `blended ∈ [min(component values), max(component values)]`; higher `r` ⇒ lower DCF;
  scenario ordering bear ≤ base ≤ bull for monotonic assumptions.
- **Purity:** no I/O; deterministic for given inputs (testable in isolation, [07 §5](07-testing-and-quality.md)).

## 6. Scenarios & blended fair value

- **Scenarios** = assumption override sets applied across models: Bear (lower growth, higher discount,
  lower terminal/multiples), Base, Bull (inverse).
- **Blended** default weights (adjustable, from original spec):
  `DCF 35% · Owner Earnings 20% · Earnings Multiple 20% · EBITDA Multiple 15% · Revenue Multiple 10%`.
  - Unprofitable co.: reduce DCF/earnings weights, raise revenue-multiple weight.
  - Dividend payer: include DDM in the blend.
  - Banks/financials: exclude EBITDA & standard FCF models; use book value / ROE / P/E (documented
    profile-based weight presets).
- **Margin of Safety** = `(FairValue − CurrentPrice)/FairValue`.
- Weights renormalize to 100% when models are excluded; the applied weights are stored.

## 7. Data requirements & sources

- Endpoints: `GET /api/v1/valuation/{ticker}` (defaults), `POST` (custom assumptions),
  `GET .../history` ([04](04-api-contract.md)).
- Inputs assembled by the service from fundamentals/cash-flow ([12](12-financial-statements.md),
  [13](13-cash-flow-analysis.md)), price (current), and peers ([15](15-peer-comparison.md)).
- Results persisted to `valuation_results` with full assumptions ([03](03-data-model.md)).

## 8. UI/UX

- `FairValueRange` (bear/base/bull/blended vs current price), `ValuationSummary` (MoS), per-model
  breakdown cards showing inputs + intermediates, and `ScenarioInputs` to edit assumptions and
  recompute ([06](06-design-system-ui.md)).
- Every assumption labeled with its default and source; "reset to defaults" available.

## 9. Edge cases & error handling

- `r ≤ g` → reject with a clear message (don't compute a nonsensical TV).
- Negative/zero FCF or EPS → DCF/earnings models return `not_applicable`; blend reweights to remaining.
- Extreme multiples / growth → soft-warn the user (sanity bounds) but allow (their assumptions).

## 10. Testing requirements (highest rigor — see [07 §5](07-testing-and-quality.md))

- Worked-example unit test per model vs hand-computed expected output (±0.5%).
- Property tests: monotonicity (r↑⇒DCF↓), blended within component bounds, MoS sign correctness.
- Edge tests: `r≤g` errors; non-payer DDM → not_applicable; bank profile excludes EBITDA/FCF models.
- Reproducibility: recompute from stored `assumptions_json` yields identical result.

## 11. Open questions & assumptions

- Bank/financial valuation depth (P/B, ROE-driven) — **assume** a basic preset in Phase 4, deepen later.
- Default growth assumptions: **assume** derived from trailing fundamentals with conservative caps.

## 12. Done criteria

- All seven models implemented as pure functions with tests; scenarios + blended FV + MoS compute;
  assumptions editable and persisted; history retrievable.
