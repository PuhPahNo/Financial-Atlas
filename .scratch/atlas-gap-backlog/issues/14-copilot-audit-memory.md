# Copilot Audit Trail And Memory

Status: implemented

## Problem

Copilot state changes need visible provenance so the user can understand what happened and why.

## Scope

- Show session history, pending actions, confirmed actions, and rejected actions.
- Summarize long-running sessions without losing important strategy context.
- Link created strategies, runs, and accounts back to assistant messages.

## Acceptance Criteria

- Every confirmed write action is traceable to a user message and assistant plan.
- Session summaries preserve model names, tickers, parameters, and account assignments.
- UI can display action status without reading raw database rows.

## Implementation Notes

- Enriched assistant pending-action payloads with `_assistant` context containing session ID, source message ID, and Copilot provenance.
- Confirmed write actions now persist `result_ref` metadata back onto the action payload.
- Assistant API responses now include formatted `actions` history and parsed session `memory`.
- Copilot-created strategies preserve assistant provenance in strategy metrics.
- Assistant-triggered backtest runs preserve `assistant_context` in saved run inputs and return run references in tool calls.
- Workflow plans preserve model, parameter, backtest, and assignment references across continue/retry/confirm steps.
- Copilot UI now renders a compact action-status panel for pending, confirmed, and rejected actions.

## QA Evidence

- `PYTHONPATH=backend pytest backend/tests/test_assistant_api.py` -> 11 passed.
- `PYTHONPATH=backend pytest backend/tests` -> 57 passed.
- `npm run build` -> passed.
- Browser smoke on `http://127.0.0.1:3000/paper-trading`:
  - Copilot create suggestion showed pending action status.
  - Rejecting the smoke action removed the pending card and left a visible rejected action status.
