# Copilot Multi-Step Orchestration

Status: implemented

## Problem

Users naturally ask Copilot for a workflow, not an isolated action. The assistant needs to plan
multi-step work while keeping confirmations clear.

## Scope

- Represent assistant plans as ordered steps with read-only and pending-write phases.
- Support create strategy, run backtest, assign to account, then explain outcome.
- Allow rejection or retry of individual steps.

## Acceptance Criteria

- Multi-step plans do not execute write actions silently.
- Confirming one write action does not automatically approve unrelated later writes.
- The assistant can resume after a confirmed step.

## Implementation Notes

- Added a lightweight `copilot_workflow_v1` plan state stored in the assistant session summary.
- Added multi-step parsing for create strategy -> backtest -> assign to account requests.
- Confirming the create step only creates the model and advances the plan to a resumable read-only backtest step.
- Saying `continue` or `retry` resumes the active plan; successful backtests stage assignment as a separate pending write.
- Rejections mark only that plan step rejected and do not roll back or silently execute later steps.

## QA Evidence

- `PYTHONPATH=backend pytest backend/tests/test_assistant_api.py` -> 11 passed.
- `PYTHONPATH=backend pytest backend/tests` -> 57 passed.
