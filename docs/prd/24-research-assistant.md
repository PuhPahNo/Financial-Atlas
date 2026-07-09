# 24 — Research Assistant

> Parent: [00-master-prd.md](00-master-prd.md) · Conversational Atlas tool use.

## 1. Purpose / why

Add an AI assistant that can discuss investment hypotheses, explain Atlas data, propose strategies,
and run approved paper-trading actions through the local API.

## 2. User stories & acceptance criteria

- *As a user,* I can have a multi-turn conversation about companies, models, and strategies. **AC:**
  sessions persist messages and carry recent context plus summaries.
- *As a user,* I can ask about free cash flow, profitability, capital expenditures, valuation, prices,
  filings, and strategy performance. **AC:** the assistant uses Atlas tools instead of guessing when
  data is available.
- *As a user,* I can ask the assistant to create or update a model. **AC:** state-changing tool calls
  require explicit confirmation before they execute.
- *As a maintainer,* secrets stay server-side. **AC:** `OPENAI_API_KEY` is read by the backend only.

## 3. Scope (in / out)

- **In:** OpenAI-backed chat, server-side model configuration, persisted sessions, tool registry,
  read-only research tools, confirmed write tools, and audit trail.
- **Out:** autonomous real trading, personalized financial advice, sending secrets to the browser, and
  unconfirmed destructive actions.

## 4. Tool policy

Read-only tools may run during a response. Write tools return a pending action first and execute only
after the user confirms. Delete/archive actions require the target id and label in the confirmation.

Initial tools:
- search companies
- get company overview
- get cash-flow analysis
- get valuation
- get price history
- list strategy models
- propose strategy model
- create, update, archive, or delete strategy model after confirmation
- run backtest
- list and inspect simulated trader profiles
- assign a strategy to a trader or rebalance allocations after confirmation

## 5. Memory

Assistant sessions store messages in the database. The service sends recent messages plus a rolling
summary to the LLM, keeping the context useful without sending unbounded history.

## 6. Safety and honesty

Responses must label assumptions, cite data limits, and avoid recommendations. The assistant can
describe a hypothesis or backtest, but must not tell the user what to buy, sell, or short.

## 7. Testing requirements

- Tool registry tests verify read-only vs state-changing behavior.
- Assistant service tests use a fake LLM client to validate tool-call orchestration.
- API tests cover session creation, message persistence, pending action confirmation, and rejection.

## 8. Done criteria

The assistant can discuss a model over multiple turns, query Atlas data, propose a strategy, create it
after confirmation, run a backtest, and explain the results with research-tool disclaimers.
