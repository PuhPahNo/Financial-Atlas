# Trader Account Lifecycle

Status: implemented

## Problem

Profiles/accounts can hold strategy allocations, but the lifecycle needs stronger edit, rebalance,
and continuity behavior.

## Scope

- Support allocation edits with clear cash/invested effects.
- Add rebalance preview and confirmed execution.
- Preserve account history when strategies are archived.

## Acceptance Criteria

- Allocation totals and cash percentage always reconcile to 100%.
- Rebalance previews show intended orders before state changes.
- Archived strategies remain visible in historical account context.

## Implementation Notes

- Account API responses now include `reconciled_pct`, allocation `strategy_status`, and `archived`
  flags.
- Added `/api/v1/paper-trading/accounts/{account_id}/rebalance-preview` for read-only intended
  trade previews.
- Added `/api/v1/paper-trading/accounts/{account_id}/rebalance` for confirmed rebalance execution.
- Existing archived allocations can remain on an account for historical context, while new inactive
  strategy assignments are still rejected.
- Trader cards, edit form, and detail contribution rows now show archived strategy context.
- Trader edit form shows cash/invested/total reconciliation and a before-save rebalance preview.

## QA Evidence

- `PYTHONPATH=backend pytest backend/tests/test_paper_trading_api.py` -> 11 passed.
- `PYTHONPATH=backend pytest backend/tests` -> 48 passed.
- `npm run build` in `frontend/` -> passed.
- Browser smoke on `http://localhost:3000/paper-trading` created a temporary QA trader, verified
  Edit trader showed `60% invested · 40% cash · 100% total` plus the Rebalance preview block, then
  deleted the temporary trader.
