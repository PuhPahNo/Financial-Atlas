# 0004 — Single-Tenant Authorization Boundary

## Status

Accepted

## Context

Atlas auth recognizes exactly one account: the `AUTH_USERNAME` configured in the environment.
Session tokens are HMAC-signed cookies whose `sub` claim must equal that username. Domain
entities (watchlists, strategies, trader accounts, valuation history) carry no `user_id`
column, and services fetch them by primary key with no ownership filter — for example
`get_account(account_id)` returns any account to any authenticated session.

A 2026-06 security review flagged this as a high-severity gap *if* a second user is ever
added: every user would be able to read and mutate every other user's data.

## Decision

Atlas is deliberately single-tenant. One deployment serves one person; authentication gates
the deployment as a whole, and authorization inside it is intentionally flat. We will not
speculatively add `user_id` columns or ownership filters.

## Consequences

- Adding a second account (or any shared/multi-user deployment) requires a new product
  decision and a schema migration first: `user_id` on all user-owned entities, ownership
  filters on every query, and per-user rate-limit buckets. Do not bolt a second username
  onto the current auth layer.
- Hosted deployments must remain private (login required, `AUTH_REQUIRED=true`), because
  any authenticated session has full access to all local data.
- Production deployments refuse to boot on the committed dev credentials
  (`backend/app/core/config.py`), so "private" cannot silently degrade to "default password".
