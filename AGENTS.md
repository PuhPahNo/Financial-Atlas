# Financial Atlas

Local-first stock analysis & valuation platform built on free public data (SEC EDGAR + Yahoo Finance).
Frontend: Next.js + TypeScript + Tailwind (`frontend/`). Backend: FastAPI + Python (`backend/`).
Product specification lives in `docs/prd/`. See `README.md` for the full overview.

## Agent skills

### Issue tracker

Issues and PRDs are tracked as local markdown files under `.scratch/<feature-slug>/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Canonical five-role vocabulary (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
