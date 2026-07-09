# 07 — Testing & Quality Strategy

> Parent: [00-master-prd.md](00-master-prd.md) · The quality gate that exists today and the gaps we
> still need to close.

## 1. Purpose

Keep valuation math, data normalization, migrations, API contracts, and production builds safe to
refactor. This document describes current enforcement; proposed tooling is labeled as future work.

## 2. Current acceptance criteria

- A valuation formula regression fails a hand-computed pytest assertion.
- Provider normalization and fallback behavior are exercised with deterministic fakes.
- API, auth, paper-trading, migration, cache, and backtest contracts run against an isolated temp
  SQLite database and cache.
- `make verify` must pass before a production push.

## 3. Current test layers

| Layer | Current tooling | Coverage |
| --- | --- | --- |
| Unit/domain | pytest | valuation, metrics, matching, market hours, factors, validation |
| API/contract | FastAPI `TestClient` + pytest | envelopes, errors, auth, CRUD, queue lifecycle |
| Integration | pytest + temp SQLite/cache | services, persistence, migrations, fallback paths |
| Frontend static | ESLint + strict TypeScript | unused code, type and framework checks |
| Build | Next.js production build | route compilation and server/client boundaries |
| Structural | jscpd | repeated Python/TypeScript/TSX/CSS blocks |

Backtest HTTP tests inject the deterministic fixture executor in test code. The public API cannot
select fixture data. Engine tests may call that internal fixture mode directly.

## 4. Enforced local gate

`make verify` currently runs:

1. Ruff and ESLint with zero warnings.
2. TypeScript `--noEmit` with unused locals/parameters enabled.
3. The full pytest suite with a 68% aggregate coverage floor.
4. jscpd with a 1.4% failure threshold (currently zero detected clones).
5. A Next.js production build.

The gate is local and is also run before direct pushes to `main`. A hosted GitHub Actions workflow is
not installed, so the repository must not claim that PR checks enforce it automatically.

## 5. Production proof

Render startup is the current Postgres migration integration lane. After each production-affecting
push, verify the exact live commit, startup/migration logs, `/health`, authenticated API smoke calls,
and the relevant browser flows. These checks complement tests; they are not represented as a local
test result.

## 6. Known gaps

- No frontend component/unit runner is installed.
- No checked-in Playwright end-to-end suite exists.
- No hosted Postgres service-container test runs on pull requests.
- No scheduled live-provider drift suite exists.
- Python static typing and a dedicated import-direction rule are not yet enforced.

Add these only with real tests and wiring; do not list aspirational tools as completed gates.

## 7. Fixtures and safety

- Tests set `DATABASE_URL` and `CACHE_DIR` before importing the app so they cannot mutate the dev DB
  or cache.
- Network behavior is replaced with fakes/monkeypatches where determinism matters.
- Migration tests cover idempotence and fail-closed destructive preconditions.
- Time-sensitive behavior should receive explicit dates or patched clocks.

## 8. Done criteria

The current slice is done when `make verify` is green and the changed production surface is proven
on the deployed commit. Future hosted CI/E2E work is done only when its configuration and tests are
actually checked in and running.
