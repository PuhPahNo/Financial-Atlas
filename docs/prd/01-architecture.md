# 01 — Architecture

> Parent: [00-master-prd.md](00-master-prd.md) · Defines the system shape every other PRD builds on.

## 1. Purpose / why

Establish a modular, local-first architecture that runs great on a Mac today and lifts onto a
**Render web service** later with no rewrite. The structure must keep data providers, the valuation
engine, and UI modules **orthogonal** so any one can change without disturbing the others.

## 2. User stories & acceptance criteria

- *As the maintainer,* I can run the whole stack with one command locally. **AC:** `make dev` (or
  documented equivalent) starts backend + frontend; a known ticker renders end-to-end.
- *As the maintainer,* I can add a new data provider without touching UI or unrelated services.
  **AC:** implementing the provider interface + registering it is the only change required.
- *As the maintainer,* I can deploy to Render by changing configuration, not code. **AC:** swapping
  SQLite→Postgres and local cache→hosted cache is config-only.

## 3. Scope (in / out)

- **In:** repo layout, process boundaries, config/secrets, dependency direction, environment matrix
  (local vs Render), error/logging conventions.
- **Out:** specific endpoint shapes ([04](04-api-contract.md)), schema ([03](03-data-model.md)),
  provider catalog ([02](02-data-sources.md)).

## 4. Repository layout

```txt
financial-atlas/
  docs/prd/                      # this PRD set
  backend/
    app/
      api/                       # FastAPI routers (thin; no business logic)
        company_routes.py
        price_routes.py
        financial_routes.py
        valuation_routes.py
        ownership_routes.py      # insider + institutional
        filings_routes.py
        screener_routes.py
        watchlist_routes.py
      services/                  # orchestration: fetch → cache → normalize → persist
        company_service.py
        price_service.py
        financials_service.py
        valuation_engine.py      # PURE functions, no I/O
        ownership_service.py
        filings_service.py
        cache_service.py
      providers/                 # external data adapters (implement ProviderProtocol)
        base.py                  # ProviderProtocol + registry
        sec_edgar/
        fmp/
        alpha_vantage/
        twelve_data/
        finnhub/
        fred/
      models/                    # ORM models + Pydantic schemas
      core/                      # config, logging, errors, rate-limit, db session
      jobs/                      # background refresh jobs (see 05)
    tests/                       # pytest (unit/contract/integration)
    pyproject.toml
  frontend/
    app/                         # Next.js App Router pages
      company/[ticker]/
      financials/[ticker]/
      valuation/[ticker]/
      screener/
      watchlists/
    components/                  # StockChart, FinancialTable, ValuationSummary, ...
    lib/                         # api client, formatters, valuation display helpers
    package.json
  infra/                         # Render blueprint, env templates (see 30)
  Makefile                       # dev, test, lint, format entry points
```

## 5. Contracts (dependency direction)

Strict one-way dependency to preserve orthogonality:

```txt
api  →  services  →  providers  →  external sources
                 ↘  models / core (config, db, cache)
valuation_engine: PURE — depends on nothing but its typed inputs (testable in isolation)
```

- **Routers** validate input and shape responses; they contain **no business logic**.
- **Services** orchestrate (cache check → provider call → normalize → persist → derive).
- **Providers** know one source only and return **normalized** domain objects (DBC: see [02](02-data-sources.md)).
- **valuation_engine** is pure: typed inputs → typed outputs, deterministic, no network/DB.

## 6. Configuration & environments

Single typed settings object (`core/config.py`, Pydantic `BaseSettings`) sourced from env vars:

| Setting | Local default | Render |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///./atlas.db` | Postgres URL (Render-managed) |
| `CACHE_BACKEND` | `filesystem` (`./.cache`) | Render disk or Key-Value store |
| `*_API_KEY` (per provider) | `.env` (gitignored) | Render env group (secrets) |
| `JOB_SCHEDULER` | `apscheduler` in-process | Render Cron Job |
| `LOG_LEVEL`, `ENV` | `debug`, `local` | `info`, `production` |

No secrets in code or git. `.env.example` documents every variable.

## 7. Cross-cutting conventions

- **Errors:** typed exception hierarchy (`ProviderError`, `RateLimitError`, `NotFoundError`,
  `ValidationError`) mapped to the API error model in [04](04-api-contract.md).
- **Logging:** structured JSON logs with request id + ticker + provider for traceability.
- **Time/units:** store monetary values in reporting currency with an explicit `currency` field;
  store dates as ISO-8601; never mix raw and derived (see [03](03-data-model.md)).
- **Assertive boundaries:** every provider response is validated against a Pydantic schema before it
  enters a service — bad data fails fast and loud, never silently propagates.

## 8. Dependencies

- [02-data-sources.md](02-data-sources.md) (provider interface), [03-data-model.md](03-data-model.md)
  (persistence), [05-caching-and-jobs.md](05-caching-and-jobs.md) (cache/jobs),
  [30-deployment-render.md](30-deployment-render.md) (hosting).

## 9. Edge cases & error handling

- Missing provider API key → provider self-disables and is skipped in the fallback chain (logged).
- Local DB absent on first run → auto-create via migrations.
- Cold cache for a large ticker → progress states surfaced to UI; never a hard timeout failure.

## 10. Testing requirements

- Smoke test: app boots, health check passes, one ticker flows end-to-end.
- Dependency-direction guard (lint/import-linter) so layers can't import "upward".
- Config loads correctly for both local and production env matrices.

## 11. Open questions & assumptions

- Backend served standalone (uvicorn) with Next.js calling it, vs Next.js API-route proxy. **Assume**
  standalone FastAPI behind the Next.js app; revisit if Render single-service is simpler.

## 12. Done criteria

- Tracer bullet: repo scaffolds, `make dev` runs, health check green, dependency-direction guard
  enforced in CI. → Thickened as services/providers land in Phase 2.
