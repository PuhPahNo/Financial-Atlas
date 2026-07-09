# 30 — Deployment to Render

> Parent: [00-master-prd.md](00-master-prd.md) · The production shape that is actually deployed.

## 1. Purpose

Run the local-first app as one single-tenant Render service backed by managed Postgres and a
persistent cache disk, with repeatable `main`-branch deploys and fail-closed startup migrations.

## 2. Current topology

| Resource | Role |
| --- | --- |
| Docker web service | Next.js on Render's public `$PORT`; FastAPI privately on `127.0.0.1:8000` |
| Managed Postgres | application persistence via `DATABASE_URL` |
| Persistent disk | bounded provider cache and durable price data under `/var/data` |
| In-process workers | queued backtests, live account marks, nightly data maintenance |
| Render environment | credentials, provider keys, database URL, and runtime configuration |

The service is provisioned manually. `infra/render.yaml` is a reviewed reference for the same shape,
not evidence that a Blueprint owns the live resources.

## 3. Runtime contract

- `scripts/render-start.sh` starts private FastAPI and public Next.js in the same container.
- `DATABASE_URL` selects Postgres; local development defaults to SQLite.
- `CACHE_DIR=/var/data/cache`, `CACHE_MAX_MB`, and `CACHE_MIN_FREE_MB` bound disk usage and preserve
  free space for Postgres-adjacent durable data.
- FastAPI startup creates missing tables, reconciles additive columns, then runs the ordered
  `atlas_schema_migrations` revisions transactionally.
- Destructive migrations validate production data and raise before DDL when a precondition fails.
- `DATA_MAINTENANCE_*` and `LIVE_MARK_*` control the in-process loops. No Render Cron Job is required.

## 4. Deploy flow

1. Run `make verify` locally.
2. Push the reviewed commit to `main`.
3. Render builds a replacement container from that exact commit.
4. Startup migrations finish before the health check can pass.
5. Render switches traffic only after the new instance is healthy; a startup failure leaves the
   previous instance available.

## 5. Authentication boundary

The deployment has one owner. Read-only company/market research remains public. Login is required
for user-owned or mutating workflows: paper trading, backtests, assistant sessions, watchlists,
screener workspace operations, and custom valuation writes. `AUTH_REQUIRED=true` and non-default
production credentials are mandatory. See [ADR 0004](../adr/0004-single-tenant-authorization-boundary.md).

## 6. Required configuration

- Required: `DATABASE_URL`, `BACKEND_URL=http://127.0.0.1:8000`, `ENV=production`,
  `SEC_USER_AGENT`, `AUTH_USERNAME`, `AUTH_PASSWORD`, and `AUTH_SECRET`.
- Persistent cache: `CACHE_DIR`, `CACHE_MAX_MB`, `CACHE_MIN_FREE_MB`.
- Optional providers: `OPENAI_API_KEY`, `FMP_API_KEY`, and `FINNHUB_API_KEY`.

Secrets live in Render; committed config contains no values.

## 7. Production verification

For every production-affecting push:

- Confirm Render's live deployment commit equals the pushed `main` commit.
- Inspect startup and migration logs for errors.
- Check `/health`, login, protected-route rejection, representative research/provider APIs,
  strategies, accounts, backtests, watchlists, and browser console errors.
- Exercise only read-only production calls unless a mutation was explicitly authorized.

Render startup is the current Postgres migration proof. There is no hosted preview/staging service or
Postgres CI lane today; [07](07-testing-and-quality.md) records that gap.

## 8. Edge cases

- Cold starts may delay the first request; health and smoke checks should retry during cutover.
- Provider keys are optional and unavailable sources degrade with explicit warnings.
- Cache pruning reserves disk space before writes and retries after pruning.
- Queued jobs interrupted by a deploy are marked failed on boot and can be rerun.

## 9. Done criteria

The exact pushed commit is live, migrations completed, health is green, authenticated and public
read paths work, background pipelines show no startup errors, and the relevant browser flows have no
regression.
