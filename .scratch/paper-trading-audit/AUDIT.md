# Paper Trading & Strategy Platform — Exhaustive Audit

**Date:** 2026-07-01
**Scope:** strategy building (Build tab, Copilot), backtesting (Backtest Lab, engine, sweeps), model catalog, trader accounts (assignment, live valuation), the vestigial paper-portfolio layer, tests, and docs/PRD alignment.
**Method:** five parallel deep code audits (paper-trading engine, backtesting engine, strategy lifecycle wiring, frontend UX, tests/docs) plus a live UI walkthrough in which several findings were reproduced end-to-end against the running app.

---

## 1. The reality check — what the system actually is

This is the honest architecture, which nothing in the UI states outright:

- **There is no live trading engine.** A trader account is `starting_cash` + strategy weights. Its holdings are *derived state*: each trading day, every sleeve's deterministic EOD backtest is re-run over a rolling ~3-year window (`accounts.py _compute_holdings`), and the ending open positions become the account's "settled holdings" (cached for the trading day). During market hours those settled shares are marked to ~15-minute-delayed Yahoo quotes on a 60-second loop. No intraday order is ever placed; signals materialize as positions only when the next day's re-simulation includes them.
  - This design is genuinely clever: signals can't double-fire, restarts self-heal, and live behavior is *by construction* the same code as the backtester — there is no second rule interpreter to drift.
  - Its cost: **ledger semantics don't exist.** Performance history is a re-simulation that rewrites itself (monthly window shifts, any strategy edit, any starting-cash change), and the UI presents that synthetic backfill as a real track record (see 3.6).
- **Two backtest paths, one dispatcher** (`engine.py run_backtest`): a signal-rule engine (next-bar fills) and an active S&P 500 / fixed-basket screener (eligibility at day d−1, fill at day d close, PIT fundamentals + PIT index membership). Buy-and-hold is dead code except under fixtures.
- **`PaperPortfolio`/`portfolio.py` is a vestigial toy** that ignores strategy logic entirely (buys `tickers[0]` once, no sells, no costs, no marking). It is unreachable from the current UI but still exposed via API and an assistant write tool.
- **The Copilot is a deterministic parser** (not an LLM) with confirm-gated writes going through the same validator as the UI.
- **The Build tab's "projected equity" is a seeded random walk** (`ptdata.ts project()`), not a simulation. It is labeled "Saved projection" after save — but the knobs themselves are largely placebo (see 3.1).

### Backtest-integrity invariant check (the "no cheating" contract)

| Invariant | Verdict |
|---|---|
| Adjusted closes only | **HOLDS** — with silent-degradation caveats (3.2, 3.3) |
| Next-bar execution, no same-bar signal+fill | **HOLDS** (both engines, regression-tested) |
| PIT fundamentals v3 (earliest-filed, restatements dropped) | **HOLDS** |
| Integrity report attached & persisted per run | **HOLDS for single runs; REGRESSED for sweeps** — `run_parameter_sweep` persists runs with no `integrity` key (`service.py:427-439`) |
| Fixed-basket models trade only declared tickers; index models PIT-gated | **HOLDS** — but payload/model tickers are folded into the index superset as permanent members, bypassing the membership gate (`engine.py:404-416`) |

---

## 2. Reproduced live in this session (evidence, not hypothesis)

1. **Long backtests die at the Next dev proxy; the engine keeps going.** Clicking "Backtest in lab" on FCF Compounder (GFC regime) auto-ran a ~45–75s backtest; the proxy killed the POST (`ECONNRESET "socket hang up"`), the UI showed a bare **"Request failed (500)"**, and I retried twice — the backend completed and persisted **all three runs** (`backtest_runs` 742–744, duplicates) that no UI can ever display. Quick runs (<~30s) complete fine. Root cause is architectural: `POST /api/v1/backtests` is synchronous with no job lifecycle (§3.5). Note: the prior memory of this gotcha ("restart-poisoned keep-alive pool") is wrong or incomplete — a fresh proxy with healthy GETs still killed every slow POST.
2. **Ghost backtest attribution via SQLite id reuse.** My freshly created "Audit Test Rule" (strategy id 31) instantly owned **44 pre-existing `backtest_runs` rows** dating to June 3 ("Assistant Generated Model", "Acct Test Strategy"…). `conftest.py` cleans test strategies by name but orphans their runs; SQLite recycles the freed id; the next real strategy inherits them. (Also: the pytest suite writes to the real dev `atlas.db` — running the test suite during this audit created runs 738–741.)
3. **Copilot "% drop" strategies are un-creatable and fail silently.** "When the S&P 500 drops by 5%, buy SPY…" → confirm card → Confirm → backend `400` (the parser omits `window_days`, which its own validator requires: `assistant/service.py:644-649` vs `validation.py:205-214`) → **no error shown, card stays PENDING, button appears dead** (`Copilot.tsx confirm()` has no catch).
4. **Any navigation destroys the Copilot session.** Clicking a sidebar item unmounts the chat; returning starts a blank session. My pending confirm card was stranded in the DB as "pending" forever.
5. **The money inputs fight the user.** In New Trader, typing "5" (first keystroke of 50000) instantly rewrites the field to "1000" (`Math.max(1000, parseInt(...))`). Same control in BacktestLab.
6. **Fabricated Sharpe is visible on the catalog.** FCF Compounder and Magic Formula cards both show Sharpe **2.40** — the exact clamp ceiling of the client-side formula `clamp(cagr/max(8,|maxDD|)+0.6, 0.3, 2.4)` (`ptdata.ts:134`), displayed under a green "Backtested" badge while the real Sharpe sits unused in the persisted run.
7. **Synthetic backfill presented as track record.** "The Quant" (trader) shows "+242.6% · from $100,000 · 2023-07-01 → 2026-07-01" — a rolling 3-year re-simulation implying three years of live history regardless of when the account was created. No disclosure on the screen.
8. **The happy path genuinely works and is honest.** Signal-rule creation → validation → auto-backtest of "buy SQQQ at S&P all-time highs" correctly produced a catastrophic −54.2% with a plain-language verdict, full risk panel, 80 fills, and an expanded integrity panel (next-bar execution, 10 bps costs, EOD caveat). The core loop is real and the integrity UX is excellent.

---

## 3. Critical findings (fix first)

### 3.1 The Builder silently destroys strategies and its knobs are placebo
- Editing **any** non-rule model routes into the guided-knobs Builder (`page.tsx` `onEdit`, ModelDetail "Tune"). `knobsFromModel()` flattens the strategy to six knobs; `knobsToPayload()` (`ptdata.ts:326-337`) then **replaces `parameters` wholesale** with `{tickers:["SPY"], risk, stop_pct, ...}` — the `model` key (`f_score`, `magic_formula`…), thresholds, and the real ticker basket are all dropped. Because accounts re-run backtests from *current* parameters, saving one slider edit **rewrites the entire history, holdings, and live mark of every allocated trader** with no warning or version record.
- The knobs the Builder does save are mostly **never read by the engine**: it reads `take_profit_pct`/`stop_loss_pct`/`max_hold_days`/`max_positions`, while the Builder writes `stop_pct`, `hold_days`, `risk`, `leverage`, `trend_filter`. A user setting "Stop loss 8%" gets the category default 12%; "Leverage 3x" does nothing.
- With the legacy `StrategyEditor` dead (§6), **no working UI can correctly tune a model-library strategy.**

### 3.2 Price store silently sheds small dividend adjustments (`price_store.py:90-104`)
Tail-merge re-adjustment detection uses a 0.5% tolerance over the last 5 overlapping bars. Quarterly dividends re-base prior history by 0.1–0.4% for most large caps — **below tolerance** — so nightly warm appends permanently keep un-re-based history. Low-yield names decay toward split-only price series; a 10-year SPY benchmark loses much of its ~1.3%/yr dividend return; dividend-strategy-vs-SPY comparisons skew asymmetrically — while the integrity report claims "dividend income isn't dropped." Self-heals only on a full refetch. **Related:** the Stooq fallback stores split-only closes labeled adjusted (`stooq.py:66-68`), and per-bar raw-close fallback can mix bases within one series (`price_store.py:45`).

### 3.3 Survivorship can silently return — while grading itself "pass" (`universe.py:141-179`)
Any failure fetching the S&P change-log returns `[]`; `members_on` then reconstructs from zero changes = **today's index**, memoized for the process. The integrity report grades membership "pass" purely because the lambda exists. One bad fetch ⇒ a 2010–2015 backtest screens today's survivors under a green "no survivorship cheats" badge.

### 3.4 Halted/delisted names fill and mark at frozen prices (`screen.py:456-511`, `factors.py:30-32`)
`close_at` carries the last close forward indefinitely: a halted stock "fills," never trips its stop (price frozen), and exits at max-hold at the pre-halt price — a near-total real-world loss reported as ~0%. No delisting write-down exists anywhere; combined with the 7-day dead-ticker skiplist poisoning on *transient* fetch errors (`screen.py:46-60` — no per-run coverage disclosure), index-scan results can quietly run on a truncated, left-tail-censored universe.

### 3.5 Synchronous backtest architecture with no run lifecycle (`api/backtesting.py:19-27`, `screen.py:44`)
One process-wide blocking lock held for entire runs including cold network fetches; sync routes pin threadpool workers; no timeout, cancellation, progress, or status column — and any client/proxy timeout orphans a still-running run (reproduced, §2.1). The UI compounds it: Run is never disabled (stackable duplicate runs), ModelDetail auto-runs index-wide screeners on open with no abort on close, the auto-run effect has no cancellation so rapid regime/strategy switches race and **the last response wins even if it's for the earlier selection**, and a hidden page-mount worker runs its own queue. Recommendation: make runs a job (row with status → poll), disable Run while in flight, add AbortController + request keying, and surface a "recent runs" list (every run is already persisted but is invisible to the product — `GET /backtests/{id}` has zero UI consumers).

### 3.6 The live-account layer misrepresents freshness and history (`accounts.py`)
- **EOD baseline is a full session behind when closed:** `price_window`'s `period2` excludes the end date's bar, so Tuesday evening's "value" is built from **Monday's** closes with `day_change: 0` (heals at midnight ET).
- **Partial quote failure is invisible:** `stale` is set only if *every* quote fails; 9 of 10 legs can be end-of-day-stale with `stale: false` — and the API envelope hardcodes `meta.stale: false` regardless (`api/paper_trading.py:26-27`).
- **Holdings cache key omits strategy parameters:** edit a strategy intraday and the account keeps valuing pre-edit holdings until tomorrow.
- **A transiently failing sleeve becomes 100% cash, cached for the rest of the day** — a provider hiccup at 9:31 misvalues 40% of an account all day, flagged only in a warnings string nobody renders.
- **History rewrites itself:** monthly window-start jumps, strategy edits, rebalances, and starting-cash changes retroactively re-simulate three years at historical prices for free. `/performance` and `/value` can also disagree (windows differ; rule-engine end-liquidation vs screener no-liquidation).

### 3.7 Silent failure is the default UI error strategy
Reproduced twice live (§2.1, §2.3); the pattern is systemic: initial page load has **no catch** — a down backend renders as "No models here yet" plus a hard-coded fake "$128,440" desk card (`page.tsx:44-52,179`); ModelDetail/warm-worker/Copilot all swallow errors (`catch {}`); the single toast is always styled as success; FastAPI 422s bypass the error envelope so users see "Request failed (422)"; the validator's field-level `issues` array is never rendered by any surface.

---

## 4. Major findings

### Realism & honesty gaps
| # | Finding | Where |
|---|---|---|
| R1 | **Seed catalog describes behavior the engine doesn't execute.** ~18 dead parameter names (`channel_days`, `premium_pct`, `rebalance_days`, `max_short_exposure`…) have zero readers. "Mean Reversion Guardrail" ("buys after oversold moves") actually runs a **momentum** gate (px>SMA100, mom>0) — the opposite. All three "Options" models degrade to a plain SMA-200 trend-long; no options math exists. The sweep UI even offers to sweep dead params (N identical runs). | `seed_catalog.py` vs `screen.py:286-353` |
| R2 | Legacy seeds ship invented `backtested_return`/`win_rate` in the same field real backtests overwrite — fiction indistinguishable from measurement on a fresh install until the bootstrap refresh lands. Contradicts the catalog's own stated principle (`seed_catalog.py:227-231`). | `seed_catalog.py` |
| R3 | Card "Return" is multi-year total return under a tooltip claiming CAGR (`ptdata.ts:93` vs `STAT_TIPS.cagr`). Plus fabricated trade counts (`40 + hash%400`), invented equal-weight donut with hard-coded 82% invested, fake desk sparkline. | `ptdata.ts`, `ModelDetail.tsx` |
| R4 | No intraday execution for accounts, but nothing says so: users will assume stops fire intraday; they only evaluate at closes inside the daily re-simulation. Live "fills" in the legacy portfolio path use an in-progress partial bar with zero costs while backtests charge 10 bps. | `accounts.py`, `portfolio.py:117-126` |
| R5 | Shorts are frictionless (no margin/borrow/forced liquidation; sleeve equity can go negative and keep trading); screener buys fractional shares vs rule engine integer shares. | `screen.py:517-523`, `engine.py:304` |
| R6 | Benchmark is frictionless/fully-invested vs strategy at 95%/costs — fair convention, but undisclosed, and "alpha" is just excess total return while the real regression alpha is computed and discarded (`metrics.py:116,133`). | `metrics.py` |

### Lifecycle & Copilot
| # | Finding | Where |
|---|---|---|
| L1 | Backtest validation isn't pinned to assignment: accounts always run the rolling 3-year window regardless of what regime the user validated; no strategy versioning or edit audit trail (the per-run `strategy_snapshot` already persisted is the raw material for fixing this — currently unused). | `accounts.py:285-287,449-453` |
| L2 | Copilot "create … for AAPL MSFT" silently creates an **index-wide S&P screener** (no `universe` key ⇒ index routing; the named tickers just join the superset). The confirm card says "AAPL, MSFT". That exact phrasing is a suggested prompt in the UI. | `assistant/service.py:375-389`, `engine.py:392-416` |
| L3 | Clones copy `metrics_json` verbatim ⇒ "Backtested" badge, window, and curve from the *source*; assistant-cloned models have no auto-backtest, so the false provenance persists until the nightly refresh. | `service.py:190-192` |
| L4 | Archiving has no in-use check; archived strategies **keep trading in every allocated account** but 404 on edit, with no unarchive route — a bad archived sleeve can never be fixed, only de-allocated. The delete-confirm copy ("allocations keep their stored snapshots") is false. | `service.py:204-212`, `accounts.py:50-72` |
| L5 | Assistant rebalance **replaces all allocations** with only the sleeves mentioned — "rebalance to 30% Dual Momentum" silently liquidates everything else; the confirm card doesn't show what's dropped. Assign/resolve use ≥1-token fuzzy matching on writes. | `assistant/service.py:491-521`, `accounts.py:120-137,221-226` |
| L6 | Assistant `run_backtest` is classified read-only (no confirmation) but persists runs — breaks the "writes require confirmation" contract. Nightly headline refresh also persists a full run per strategy (~25k rows/night, no pruning). | `tools.py:15-27`, `refresh_headlines.py` |
| L7 | `POST /strategies/validate` has zero callers; RuleBuilder re-implements validation client-side (in sync today; the assistant path already drifted exactly where the mirror doesn't apply — §2.3). | `paperTradingApi.ts`, `ptdata.ts:258-284` |
| L8 | Catalogue strategies accept arbitrary params that the engine casts unguarded — `max_hold_days: "one year"` ⇒ raw 500 from `run_backtest`, or a sleeve silently zeroed to cash inside an account. Percent/fraction heuristic makes values in (1,2] unexpressible (1.5 meaning 150% reads as 1.5%). | `validation.py:130-149`, `screen.py:306-348` |

### Frontend UX
| # | Finding | Where |
|---|---|---|
| U1 | Invisible favorite star (`opacity:0`, still mounted) sits exactly over the hover Edit/Trash buttons — clicks aimed at destructive actions can silently toggle favorite instead. | `BotsView.tsx:46-54` |
| U2 | Background refresh wipes sweep config/results mid-use (memo on `parameters` object identity; every warm-worker completion rebuilds all models). | `BacktestLab.tsx:172-180`, `page.tsx:56-90` |
| U3 | Double-submit: Create & track / Create trader never disable while awaiting create+backtest; the only feedback is a 2.6s toast that dies long before the await ⇒ duplicate strategies/traders. | `Builder.tsx:110`, `TraderForm.tsx:170`, `page.tsx:92-118` |
| U4 | Client-side rebalance preview computes from *starting* cash and diverges from the backend; the real `rebalancePreview`/`rebalanceAccount` endpoints have zero callers. | `TraderForm.tsx:28-44` |
| U5 | Charts have no axes/ticks/dates at all; 0/1-point series render blank with no message; trades table renders thousands of unvirtualized rows; ISO dates in tooltips vs ET everywhere else. | `ptcharts.tsx` |
| U6 | Custom regime dates validated only by regex (2015-99-99 passes); stale select when chosen strategy is archived (blank select, Run silently tests `models[0]`); no unsaved-changes protection on any modal/backdrop/Escape; hover-only tooltips; clickable-div cards with no keyboard path or dialog ARIA. | `BacktestLab.tsx`, `ptkit.tsx` |
| U7 | Terminology drift: the same object is Model / strategy / bot; the same account is Trader / account / Paper desk; UI says "archive" while the API responds `{"deleted": id}` and archives. | everywhere |

### Tests & docs
| # | Finding | Where |
|---|---|---|
| T1 | **The fundamental-model path has zero end-to-end coverage** — and a test-file comment claims that coverage exists (it was dropped in the active-engine rewrite). A look-ahead regression in `as_of` wiring would pass the suite green. | `test_screen_backtest.py:3-4` |
| T2 | Short-direction execution (cover P&L, short cash handling) never runs under test anywhere positions are created; a sign error would be invisible. | `engine.py:263-311` |
| T3 | Metrics asserted only as non-None/sign — no hand-computed values for CAGR/drawdown/win-rate/Sharpe, which PRD 23 §7 explicitly requires. `service._daily_sharpe` duplicates `metrics.sharpe`. | `tests/`, `metrics.py` |
| T4 | Tests run against the shared dev `atlas.db` with name-based cleanup — proven destructive in this session (§2.2: ghost runs, id reuse). Use a temp DB fixture. | `conftest.py:16-104` |
| T5 | Untested: `_compute_holdings` (mocked in every value test), the tick loop, warm jobs, rate limits on paper-trading routes, 401s on `/backtests*`, the entire frontend (no runner configured). | — |
| T6 | `docs/prd/04-api-contract.md` lists none of the shipped surface (accounts, sweeps, validate, warm); PRD 22's portfolio spec is ~60% real (no short fills/rejected orders/equity snapshots); `docs/agents/domain.md` promises a root `CONTEXT.md` that doesn't exist. | `docs/` |

---

## 5. Minor / polish (selected)
- `max_hold_days` compares **calendar** days (252 default ≈ 8.3 months, not a trading year) — `screen.py:472`, `engine.py:287`.
- `metrics["trades"]` counts entries+exits (reads as double round-trips next to win-rate on exits only).
- Beta pairs strategy/benchmark returns by tail position, not date (`metrics.py:84-87`).
- Same-close TP re-entry churn (exit and re-buy the same name at the identical close, paying two fills).
- Day-0 entry costs appear in total return but not the Sharpe return series (Sharpe slightly flattered).
- NYSE holiday table ends 2027; half-days treated as full sessions.
- Mixed price bases in the live mark on ex-dividend days (adjusted store close vs raw quote previous-close) — phantom intraday drop.
- `ensure_seeded()` writes on every list/get (first-boot race ⇒ 500); slug uniqueness race on concurrent same-name creates.
- Concurrent lost-update races: `portfolio.cash` read-modify-write; rebalance delete-then-reinsert; nightly headline job vs user edits on `metrics_json` (last-writer-wins).
- "Weak FCF Short" seed ships BBBY (delisted) ⇒ silently skiplisted universe of GME/AMC.
- Assistant maps "nasdaq 100"/"qqq" → `^IXIC` (Composite, not NDX-100).
- Copilot claims "open the Backtest tab to see the fills" but the Lab can only re-run, never load a stored run.
- Self-referencing pct signals render wrongly in RuleBuilder (reference select only lists four indices).
- Cash can go microscopically negative (fee charged after `min(target, cash)` sizing).

## 6. Dead code to delete or resurrect
Eight components in `components/paper-trading/` are imported nowhere: `AssistantPanel`, `BacktestPanel`, `CategoryTabs`, `EquityCurveChart` (the only recharts usage — with real axes!), `HoldingsChart`, `ModelCard`, `StrategyEditor` (the only UI that could author raw model params), `TradesTable`. They form a parallel, diverged design system and a trap for future edits. Backend: `portfolio.py` run path (plus its API routes and assistant tool), buy-and-hold engine branch, `_window`, `defaults_json`, stale `engine.py` docstring.

## 7. Strengths — do not regress
- **Next-bar discipline implemented independently in both engines and regression-tested**; PIT fundamentals v3 (earliest-filed, restatement-dropping, version-stamped) is unusually rigorous for a free-data stack; PIT membership with removed names actually priced and entry-time-only gating.
- **Semantic parity by construction** — live accounts re-run the same engine as the Lab; one freshness-gated code path for polled and on-demand marks.
- **The integrity report** — honest per-check pass/warn/info, persisted with every run, beautifully rendered. (Fix §3.2/3.3/§4-R6 so its claims stay true, and attach it to sweeps.)
- **Provenance labeling** (Backtested / Seeded estimate / Saved projection) — right pattern, undercut only by the fake Sharpe/CAGR mislabels.
- **RuleBuilder validation UX** (field-level errors, disabled submit, live plain-English rule sentence) is exemplary; single `validate_or_raise` authority on every mutating path including the assistant; confirm-gated assistant writes.
- Fault isolation everywhere (per-sleeve, per-ticker, per-account, provider chains); engine lock as OOM guard; durable price store with re-adjustment detection (right concept — tolerance needs recalibration); dead-ticker skiplist; FMP quota discipline; auth + rate limits on all routes.
- Deterministic-fixture path segregated and integrity-labeled; warm-up history so day-one indicators are legitimate; exact-value tests where they exist (rebalance dollars, attribution reconciling to zero) are genuinely good.

## 8. Suggested priority order

**P0 — trust-destroying or data-destroying**
1. Builder parameter wipe + placebo knobs (§3.1) — block "Tune" for model-library strategies until a real editor exists; map knobs to the params the engine reads.
2. Price-store dividend decay (§3.2) — tighten tolerance below the smallest quarterly dividend ratio or compare cumulative drift; audit stored series for split-only contamination (incl. Stooq-seeded).
3. Membership degrade ⇒ "pass" (§3.3) — grade `warn`/fail the run when the change-log is empty; don't memoize a degraded universe.
4. Fake Sharpe / total-return-as-CAGR on cards (§2.6, R3) — read the persisted real metrics.
5. Test isolation (T4) — temp DB fixture; stop polluting `atlas.db`; fix orphaned-run cleanup.

**P1 — correctness & core UX**
6. Async backtest jobs + run history UI + Run-button discipline + AbortController (§3.5, §2.1).
7. Frozen-price fills/no delisting write-down + skiplist disclosure (§3.4).
8. Error surfacing pass: page-load catch, Copilot confirm/send errors, render validator `issues`, error-styled toasts (§3.7, §2.3).
9. Live-value freshness honesty: include end-date bar, per-leg staleness, param-aware cache key, sleeve-failure disclosure (§3.6).
10. Copilot pct-drop `window_days` (§2.3) + two-ticker-becomes-index routing (L2) + rebalance drops unmentioned sleeves (L5).
11. Seed catalog truth pass: delete dead params, rename/re-describe models to what they execute, drop invented metrics, replace BBBY (R1, R2).

**P2 — hardening & polish**
12. Archive lifecycle (in-use check, unarchive, honest copy) (L4); clone metrics reset (L3); sweep integrity persistence.
13. Money inputs, sweep-reset race, double-submit guards, favorite-star hit-target, chart axes/empty states, a11y basics (U1–U6, §2.5).
14. Fundamental-gate E2E test, short-execution test, hand-computed metrics tests (T1–T3).
15. Delete the eight dead components (salvage EquityCurveChart's axes, StrategyEditor's param editing) and `portfolio.py`, or finish them (§6).
16. PRD/docs sync + one glossary (model/strategy/bot, trader/account) (U7, T6).
