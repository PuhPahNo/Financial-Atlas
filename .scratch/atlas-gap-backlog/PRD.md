# Atlas Gap Backlog

Status: ready-for-agent

## Purpose

Convert the recent full QA findings into a staged implementation backlog across regular financial
analysis, paper trading, and AI Copilot. The goal is to improve speed, trust, and workflow continuity
without replacing the existing architecture or duplicating endpoint logic.

## Product Outcomes

- Company pages feel instant on warm cache and avoid avoidable request fan-out.
- Financial analysis explains metric quality, source freshness, and valuation assumptions clearly.
- Paper Trading supports repeatable model-building, backtesting, account assignment, and profile
  review with clean seeded-vs-user semantics.
- AI Copilot can safely plan and execute multi-step research workflows through confirmed tool calls.
- Regression checks cover the full happy path the user actually QA'd: financial tabs, model creation,
  backtest, profiles/accounts, Copilot-created model, assignment, and cleanup.

## Workstreams

### Financial Analysis And Data

1. Unified company snapshot API for overview data.
2. Cache metadata, stale flags, warnings, and single-flight behavior for hot ticker paths.
3. Financial quality scorecards for cash conversion, capital allocation, balance sheet, growth, and
   profitability.
4. Valuation diagnostics for assumptions, sensitivity, model applicability, and historical runs.
5. Screener universe ingestion and warm-cache jobs for tracked or popular tickers.
6. Provider fallback transparency and partial-data warnings in API and UI.

### Paper Trading

7. Strategy rule DSL validation and clearer model configuration state.
8. Model versioning and parameter-sweep backtests.
9. Trader/account lifecycle: allocation edits, rebalancing, and account state continuity.
10. Risk dashboard and performance attribution for profiles and strategies.
11. Seeded-vs-backtested metric semantics and empty/loading/error states.

### AI Copilot

12. Tool registry coverage for paper-trading actions, including account assignment.
13. Multi-step Copilot orchestration with separate confirmations for state-changing actions.
14. Copilot audit trail, session memory, and visible action provenance.
15. End-to-end regression QA suite spanning API, services, and browser flows.

## Phasing

### Phase 1: Fast Overview Path

Add a read-only company snapshot endpoint that composes existing services and lets the overview page
load from one API request. Preserve existing granular endpoints for detail tabs and compatibility.

### Phase 2: Financial Trust Layer

Make analysis deeper and more explainable: derived metric diagnostics, source/warning metadata,
valuation assumptions, sensitivity tables, and cached-provider transparency.

### Phase 3: Discovery And Universe

Improve screener ingestion, peer fallbacks, watchlist-driven warm jobs, and cross-company comparison.

### Phase 4: Paper Trading Core

Strengthen rule validation, strategy versions, parameter sweeps, risk metrics, and trader account
workflows.

### Phase 5: Copilot Workflow

Move from single assistant actions to safe multi-step plans: create model, backtest, assign to
profile, explain results, and keep an audit trail.

### Phase 6: Regression QA

Codify the full manual QA path in repeatable API and browser checks.

## Acceptance Criteria

- Every issue below has a targeted test or documented manual QA check.
- New endpoints preserve the `/api/v1` envelope contract and do not break existing routes.
- State-changing Copilot tools always require confirmation.
- Paper Trading never presents seeded illustrative metrics as user backtest results.
- Cache improvements expose `served_by`, `stale`, and warnings rather than hiding provider gaps.

## Out Of Scope

- Real brokerage execution or live-money workflows.
- Paid market data dependencies as a prerequisite for these improvements.
- A full redesign of the Paper Trading visual theme.

