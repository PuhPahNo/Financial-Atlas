# Copilot Tool Coverage

Status: implemented

## Problem

Copilot can propose and create strategies, but full workflow coverage requires tools for backtesting,
assignment, account review, and safe updates.

## Scope

- Confirm current create, backtest, and assignment tools.
- Add missing update, clone, list account, and account performance tools where useful.
- Keep every write tool behind explicit confirmation.

## Acceptance Criteria

- Copilot can create a model, run a backtest, and assign the model to a profile.
- Write actions return pending actions with human-readable payloads.
- Tests cover read-only versus state-changing tool behavior.

## Implementation Notes

- Expanded the assistant tool registry with account/profile reads, account performance, rebalance preview, strategy validation, clone strategy, and rebalance account tools.
- Kept all state-changing tools routed through `AssistantPendingAction` confirmation records.
- Added human-readable `action_summary` and `action_details` payloads for pending writes, and updated the active Copilot UI to render those instead of raw JSON.
- Added parser coverage for account profile listing/performance, model cloning, and account rebalancing.

## QA Evidence

- `PYTHONPATH=backend pytest backend/tests/test_assistant_api.py` -> 8 passed.
- `PYTHONPATH=backend pytest backend/tests` -> 54 passed.
- `npm run build` -> passed.
- Browser smoke on `http://127.0.0.1:3000/paper-trading`:
  - Copilot empty state rendered.
  - Read-only “List my strategies” suggestion returned a response with no pending action.
  - Create-model suggestion showed a readable pending action card.
  - Rejected the smoke pending action and confirmed no local strategy data was changed.
