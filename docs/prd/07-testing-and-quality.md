# 07 — Testing & Quality Strategy

> Parent: [00-master-prd.md](00-master-prd.md) · How we keep a multi-source, multi-model platform
> correct and maintainable.

## 1. Purpose / why

Define the test pyramid, the special rigor for valuation math and data normalization, CI gates, and
the Pragmatic Programmer practices (assertions, Design by Contract, tracer bullets) that keep the
codebase trustworthy as it grows.

## 2. User stories & acceptance criteria

- *As the maintainer,* a wrong valuation formula fails CI. **AC:** valuation unit tests assert against
  hand-computed reference values within ±0.5%.
- *As the maintainer,* a provider returning bad data fails fast. **AC:** contract tests reject
  non-conforming provider output before it reaches a service.
- *As the maintainer,* I can refactor a provider without breaking the UI. **AC:** API contract tests
  + e2e smoke stay green.

## 3. Scope (in / out)

- **In:** test types/layers, fixtures strategy, CI, lint/format/type gates, DBC & assertion policy.
- **Out:** per-feature acceptance criteria (each feature PRD's §2 and §10).

## 4. Test pyramid

| Layer | Tooling | What it covers |
| --- | --- | --- |
| **Unit** | pytest | valuation engine (pure fns), normalization maps, formatters, derived metrics |
| **Contract — providers** | pytest + recorded fixtures (VCR-style) | every provider satisfies `ProviderProtocol` postconditions ([02 §4](02-data-sources.md)) |
| **Contract — API** | pytest + httpx | responses validate against Pydantic models + error mapping ([04](04-api-contract.md)) |
| **Integration** | pytest + temp SQLite/Postgres | service → cache → DB → derived path; fallback engine; rate limiter |
| **Frontend unit/component** | Vitest + React Testing Library | `MetricCard`, `FinancialTable`, `StateView` incl. null/stale states |
| **E2E smoke** | Playwright | search → overview → financials → valuation render real (fixtured) data |

Paper trading adds deterministic tests around strategy CRUD, backtest accounting, portfolio fills,
and assistant tool confirmation. Backtests use tiny fixture price series before live provider data.

Most tests are fast and offline (recorded fixtures). A small, **opt-in** "live" suite hits real
providers nightly to detect upstream schema drift (kept out of the main CI gate).

## 5. Valuation engine — special rigor

The engine is pure and the riskiest correctness surface, so it gets the deepest tests:
- Each model (DCF, owner earnings, multiples, DDM, blended, MoS) has worked-example tests with
  hand-computed expected outputs ([14](14-valuation-engine.md)).
- Property tests: higher discount rate ⇒ lower DCF value; MoS sign matches price-vs-fair-value;
  blended value lies within [min, max] of component values.
- Edge cases: negative FCF, zero/negative earnings, `discount_rate ≤ terminal_growth` (must error,
  not divide-by-near-zero).

## 6. Data normalization — special rigor

- EDGAR XBRL tag normalization tested against ≥3 real companies with differing tag usage ([02 §9](02-data-sources.md)).
- Raw-vs-derived separation enforced by tests: derived values never write to statement tables ([03 §6](03-data-model.md)).
- Provenance assertion: every persisted fact row has `source` + `fetched_at`.

## 7. Design by Contract & assertive programming

- Provider methods, API endpoints, and valuation functions declare pre/postconditions; violations
  raise typed errors (not silent bad data).
- Boundary assertions validate all external input (provider responses, request params) via Pydantic.
- Internal invariants (e.g. limiter cap, blended-value bounds) guarded by assertions in dev/test.

## 8. CI gates

On every PR: `lint` (ruff/eslint) · `format` check (ruff format/prettier) · `type` (mypy/tsc) ·
`unit` · `contract` · `integration` (SQLite + Postgres) · `e2e smoke`. Import-direction guard from
[01 §5](01-architecture.md). Coverage reported (no hard % gate initially; valuation engine expected
near-100%).

## 9. Dependencies

Every PRD references this for its §10 testing requirements; [01](01-architecture.md) (layers),
[02](02-data-sources.md)/[04](04-api-contract.md) (contracts).

## 10. Edge cases & fixtures

- Fixtures are real recorded responses (anonymized keys) checked into `tests/fixtures/`, refreshed via
  a documented script — so tests are deterministic and offline.
- Time-dependent tests inject a fixed clock (no wall-clock flakiness).

## 11. Open questions & assumptions

- Postgres-in-CI via service container (assume yes). Live-provider nightly suite optional in Phase 2,
  valuable by Phase 5.

## 12. Done criteria

- Tracer bullet: CI runs unit + one provider contract test + API contract test + e2e smoke green on
  the Phase 2 slice. → Thicken per feature phase.
