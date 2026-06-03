# 0001 — Paper Trading Is Simulation Only

## Status

Accepted

## Context

Financial Atlas is a research platform. The master PRD permanently excludes brokerage integration,
order execution, and moving money. Paper trading needs simulated trades without weakening that
boundary.

## Decision

Paper trading will model strategies, portfolios, orders, fills, positions, and account value only as
local simulations. The system will not connect to broker APIs or place real orders.

## Consequences

- Every UI surface labels paper trading as simulated.
- Fills must record data source and assumption metadata.
- Future broker integrations require a new product decision and are not implied by this feature.
