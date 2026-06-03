# 22 — Paper Trading

> Parent: [00-master-prd.md](00-master-prd.md) · Simulated portfolios for research workflows.

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
- *As a user,* I can run a selected model forward in a simulated portfolio. **AC:** positions, cash,
  fills, orders, and equity snapshots are stored with source metadata.

## 3. Scope (in / out)

- **In:** simulated portfolios, strategy categories, strategy CRUD, model cards, parameter schemas,
  simulated orders/fills, positions, cash ledger, and equity snapshots.
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

Paper trading uses local persisted strategy definitions and simulated account state. Every simulated
fill records its data source, input price, execution rule, and timestamp. `user_id` defaults to
`local` until hosted accounts are introduced.

## 6. UI requirements

The top-level `/paper-trading` page shows category tabs, model cards, strategy editor, portfolio
summary, positions, trades, equity curve, holdings chart, and assistant panel. CRUD controls must be
keyboard accessible and destructive actions must be explicit.

## 7. Edge cases

- Missing price bars produce warnings and skipped fills, not fabricated prices.
- Short strategies must declare max exposure and stop-loss rules.
- Options-themed models must label synthetic assumptions.
- Deleting a model with historical runs archives it rather than removing history.

## 8. Testing requirements

- CRUD contract tests cover create, update, clone, archive/delete, and seeded-model protection.
- Portfolio tests cover cash, long fills, short fills, rejected orders, and equity snapshots.
- UI smoke test verifies `/paper-trading` renders with empty and seeded states.

## 9. Done criteria

The user can create a custom model, tune parameters, run it in a simulated portfolio, inspect
positions/trades/equity snapshots, and archive obsolete models without touching real brokerage APIs.
