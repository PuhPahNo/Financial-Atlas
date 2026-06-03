# 0003 — Free Data Backtesting Limits

## Status

Accepted

## Context

Atlas currently uses free public sources, especially SEC data and Yahoo EOD prices. Free sources do
not provide execution-grade intraday data or full historical options chains.

## Decision

Backtesting v1 uses deterministic end-of-day simulations over existing free data. Options-themed
models may use synthetic assumptions over underlying prices, but must label those assumptions.

## Consequences

- Backtests are research approximations, not execution promises.
- Missing data creates warnings instead of fabricated fills.
- Adding a new historical data provider should happen behind the provider interface.
