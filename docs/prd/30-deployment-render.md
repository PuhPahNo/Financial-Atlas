# 30 — Deployment to Render

> Parent: [00-master-prd.md](00-master-prd.md) · The local→hosted path. Configuration-driven, no
> rewrite ([01 §6](01-architecture.md)).

## 1. Purpose / why

Take the local-first app to a hosted **Render** web service when ready: Postgres instead of SQLite,
scheduled jobs as Render Cron, secrets in Render env groups, and a repeatable deploy — changing
configuration, not code.

## 2. User stories & acceptance criteria

- *As the owner,* I deploy to Render and reach the app at a URL. **AC:** frontend + backend served on
  Render; a known ticker flows end-to-end against Postgres.
- *As the owner,* data refreshes run on schedule in prod. **AC:** Render Cron Jobs invoke the same job
  functions as local ([05](05-caching-and-jobs.md)).
- *As the maintainer,* no secret is in git. **AC:** all keys/URLs come from Render env groups; repo has
  only `.env.example`.

## 3. Scope (in / out)

- **In:** Render service topology, Postgres provisioning + migration, env/secrets, cron jobs, build/
  deploy pipeline, cache backend in prod, basic auth decision.
- **Out:** multi-region/scaling (post-v1); the app features themselves.

## 4. Target topology on Render

| Render resource | Role |
| --- | --- |
| **Web Service — backend** | FastAPI (uvicorn/gunicorn); serves `/api/v1` |
| **Web Service / Static — frontend** | Next.js app calling the backend |
| **Postgres** | managed DB (replaces SQLite via `DATABASE_URL`) |
| **Cron Jobs** | invoke `jobs/` functions (`refresh_prices`, `refresh_fundamentals`, `refresh_filings`, `recompute_valuations`) |
| **Disk / Key-Value** | response cache backend ([05](05-caching-and-jobs.md)) |
| **Env group** | all `*_API_KEY`, `DATABASE_URL`, config |

Defined as a **Render Blueprint** (`infra/render.yaml`) so the topology is reproducible
infrastructure-as-code.

## 5. Contracts (config switches only)

- `DATABASE_URL` → Postgres; the tracked application migrations run during backend startup
  ([03 §7](03-data-model.md)).
- `CACHE_BACKEND` → Render Disk or Key-Value ([05](05-caching-and-jobs.md)).
- `JOB_SCHEDULER` → Render Cron (local was in-process APScheduler).
- **Invariant:** application code is identical local vs Render; only env/config differs ([01 §6](01-architecture.md)).

## 6. Migration path (SQLite → Postgres)

1. Provision Render Postgres; set `DATABASE_URL` in the env group.
2. Start the backend; tracked migrations apply transactionally before the health check passes.
3. Optional one-time data backfill (or just let refresh jobs repopulate from EDGAR — preferred, since
   the DB is a cache of public data).

## 7. CI/CD

- Run `make verify`, push `main`, then Render builds and starts the replacement instance. Migrations
  run before the backend health check; failed startup leaves the previous instance live.
- Health check endpoint gates the deploy; rollback on failed health check.

## 8. Auth decision (open)

Single-tenant today (`user_id='local'`). For public hosting, choose:
- **(a)** keep it private (single user, IP/basic-auth) — simplest; or
- **(b)** add real accounts (auth provider + `user_id` FKs on watchlists/screens).
Decision deferred to when hosting is actually pursued; **assume (a)** for first deploy.

## 9. Dependencies

[01](01-architecture.md) (config), [03](03-data-model.md) (Postgres parity), [05](05-caching-and-jobs.md)
(cron + cache), [07](07-testing-and-quality.md) (both-engine CI).

## 10. Edge cases & error handling

- Free-tier Render sleep/cold starts → background jobs keep cache warm; health check tolerant of cold
  start. Provider keys missing in env → provider self-disables ([01 §7](01-architecture.md)), logged.
- Postgres connection limits → pooled sessions in `core/`.

## 11. Testing requirements

- Migrations green on Postgres in CI; smoke test against a Render preview/staging; cron job invocation
  test (job runs idempotently in the hosted env).

## 12. Done criteria

- App reachable on a Render URL serving the full flows against Postgres, with cron-driven refresh and
  all secrets in env groups — achieved by config, not code changes.

> Note: provisioning can use the Render tooling available in this environment when this phase begins.
