# 0002 — Assistant Tool Confirmation Policy

## Status

Accepted

## Context

The research assistant can call Atlas tools. Some tools only read research data, while others create,
update, archive, or delete local strategy and portfolio records.

## Decision

Read-only assistant tools may execute during a chat turn. Any state-changing tool must first create a
pending action and wait for explicit user confirmation.

## Consequences

- Confirmations include the action, target, and payload summary.
- Pending actions are persisted for auditability.
- Destructive actions cannot be triggered solely by the language model response.
