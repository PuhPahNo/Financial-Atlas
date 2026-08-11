# Durable OpenAI budget ledger

Status: ready-for-human

Implement durable global/QA reservations, reconciliation, usage reporting, and exhaustion behavior shared by every OpenAI call.

## Comments

- Added durable conservative reservation/reconciliation across both Atlas Research and the legacy Copilot fallback.
- Automated tests cover settlement math, release on failure, global exhaustion, QA exhaustion, and reservation dominance.
- Local paid QA settled at USD 0.203911 with no outstanding reservation, leaving USD 9.796089 of the QA sub-cap.
- That exact USD 0.203911 is configured as production carryover, leaving USD 24.796089 of the project-wide cap when the production ledger is otherwise empty.
