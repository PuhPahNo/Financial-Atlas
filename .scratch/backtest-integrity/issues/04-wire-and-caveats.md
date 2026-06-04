# BI-4 — Routing + honest caveats

Status: implemented

## Scope

- `engine.run_backtest`: route real, non-rule strategies to `run_screen_backtest`. Keep
  `use_fixture_data` → buy-and-hold and `parameters.rules` → `_run_rules` unchanged.
- Append caveats to real backtest `warnings`:
  - "Point-in-time entry — positions open only when criteria were met at that date (no look-ahead)."
  - "Candidate universe is user-specified; survivorship/selection bias is not modeled."
- Frontend `ModelDetail`: show a short methodology line reflecting point-in-time + universe caveat.

## Acceptance

- Fixture + rule-based tests unchanged.
- A real (non-fixture) buy-and-hold-category model now routes through screening (no day-1 buy).
- Caveats present in API response warnings and visible in the UI.

## Test

- Existing suite stays green; new screening tests pass; `npm run build` passes.
