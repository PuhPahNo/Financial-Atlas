# 22 — Paper Trading

> Parent: [00-master-prd.md](00-master-prd.md) · Simulated trader profiles for research workflows.

## 1. Purpose / why

Give users a clean way to organize, tune, and observe trading models without real brokerage
integration. Paper trading turns Atlas research outputs into testable hypotheses while staying a
research tool, not financial advice.

## 2. User stories & acceptance criteria

- *As an investor,* I can browse several categories of trading bots. **AC:** each category has 3-5
  seeded models with profile, history, methodology, data sources, caveats, and backtested metrics.
- *As a strategist,* I can clone or create a model and tune its parameters. **AC:** parameter ranges
  are validated and saved with the strategy definition.
- *As a maintainer,* I can keep the interface clean. **AC:** user-created models support full CRUD;
  seeded models can be cloned but not destructively deleted.
- *As a user,* I can allocate one simulated trader across multiple models. **AC:** weights cannot
  exceed 100%, the unallocated remainder stays in cash, and rebalances require an explicit action.
- *As a user,* I can inspect replayed account performance. **AC:** Atlas shows the historical window,
  benchmark comparison, drawdown, strategy contributions, and a clear simulated-not-realized label.

## 3. Scope (in / out)

- **In:** trader profiles, multi-strategy allocations, rebalance preview/apply, strategy categories,
  strategy CRUD, model cards, account marks, and replayed performance/risk attribution.
- **Out:** real brokerage integrations, order execution, moving money, personalized advice, intraday
  tick simulation, and deep options-flow data.

## 4. Bot categories

- **Long-term compounders:** quality, FCF yield, owner earnings, valuation margin of safety.
- **Short-term momentum:** trend, volatility breakout, moving-average confirmation.
- **Short selling:** deteriorating fundamentals, weak price action, risk-capped borrow proxy.
- **Options-themed:** synthetic covered-call, protective-put, and volatility screens using underlying
  price data until an options-chain source is added.
- **Income and quality:** dividend durability, FCF coverage, balance-sheet quality.
- **Risk-managed rotation:** benchmark-relative strength, drawdown controls, cash fallback.

## 5. Data model

Paper trading persists strategy definitions, trader profiles, and weighted account allocations.
Performance is a reproducible replay of the current allocation over real historical prices; it is
not a realized order/fill ledger. `user_id` remains implicit until hosted accounts are introduced.

## 6. UI requirements

The top-level `/paper-trading` page shows model cards, a rule builder, backtest history, trader cards,
allocation controls, equity/drawdown charts, contribution/risk summaries, and the assistant. CRUD
controls must be keyboard accessible and destructive actions must be explicit.

## 7. Edge cases

- Missing price bars produce warnings and skipped fills, not fabricated prices.
- Short strategies must declare max exposure and stop-loss rules.
- Options-themed models must label synthetic assumptions.
- Deleting a model with historical runs archives it rather than removing history.

## 8. Testing requirements

- CRUD contract tests cover create, update, clone, archive/delete, and seeded-model protection.
- Trader tests cover allocation validation, rebalance previews, performance attribution, account
  marks, and archive/delete behavior.
- UI smoke test verifies `/paper-trading` renders with empty and seeded states.

## 9. Done criteria

The user can create and backtest a model, allocate it to a simulated trader, inspect replayed
performance and risk, rebalance the profile, and archive obsolete models without touching a broker.
