# Global Atlas Research Agent

Status: ready-for-human

## Outcome

Turn the existing paper-trading Copilot into a persistent, authenticated assistant that is available on every Financial Atlas page. It must answer difficult natural-language questions with current Atlas data, compare securities and multi-period trends, and return grounded interactive tables and charts without exposing the database or accepting arbitrary SQL.

## Product contract

- A personified Atlas analyst character follows the user globally, including paper trading. The character anchors the floating bubble, assistant voice, and panel identity; desktop uses a polished right drawer and narrow screens use a full-screen panel.
- The assistant carries one local session across page navigation and receives bounded route context (path and ticker), so a user can ask “what changed?” from a company page without restating the ticker.
- Research questions are planned by GPT-5.6 Terra through strict typed read tools over existing services. The model never receives database credentials and cannot submit SQL.
- Company overview, statements, cash-flow quality, valuation, price history, comparison, screening, filings, market context, strategies, accounts, and account performance are available through bounded tools.
- All numbers shown in charts and tables come directly from tool results. Model prose synthesizes those results and cites the named Atlas sources; it does not manufacture visualization data.
- Existing strategy/account writes keep the current explicit confirmation workflow.

## Spend and runtime constraints

- Application OpenAI spend is capped at a cumulative USD 25.00 from this release forward.
- QA-tagged usage is separately capped at cumulative USD 10.00 and also counts against the USD 25.00 global cap.
- The API key remains server-only. Every OpenAI request reserves a conservative maximum cost before it is sent, then reconciles the reservation with reported token usage.
- Budget and usage live in the existing database so restarts and deploys do not reset the cap. Concurrent requests serialize budget mutations.
- Default model and rates: `gpt-5.6-terra`, USD 2.00/M uncached input, USD 0.20/M cached input, USD 12.00/M output. All are configurable together so changing models cannot silently retain incorrect rates.
- The feature uses the existing single Render web service, database/disk, and frontend process. It adds no worker, database, Redis instance, or paid service.

## Safety and quality

- Assistant endpoints remain authenticated and rate limited.
- Tool schemas set strict bounds for ticker count, row count, history range, and lookback. Unknown tools and malformed arguments fail closed.
- Financial answers distinguish observed facts from interpretation, disclose missing/stale data, show source/provider labels, and state that outputs are research rather than personalized advice.
- Prompt injection in provider or filing content is treated as untrusted data. Tools are read-only in research mode.
- OpenAI/network/provider failures preserve the conversation and return a useful recoverable state.

## Verification

- Unit tests cover durable budget reservation/reconciliation, global and QA exhaustion, price calculation, tool schema bounds, grounded artifacts, and mocked Responses tool loops.
- Existing backend tests, frontend lint/typecheck/dupcheck/build all pass.
- Real-key local QA uses ordinary human prompts with no tool or SQL hints, records its exact cost, and stops below USD 10.00.
- Browser QA covers at least desktop and mobile widths, cross-route context, sorting/legend/tooltips, scroll/overflow, keyboard/focus behavior, and console errors.
- After local verification, push the verified main revision and confirm the exact revision and health on the existing Render service.
