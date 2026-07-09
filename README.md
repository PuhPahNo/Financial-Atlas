# Financial Atlas

Financial Atlas is a local-first stock research, valuation, paper-trading, and backtesting platform
built around free public data: SEC EDGAR, Yahoo Finance, and optional free provider keys.

The user-facing product name is **Atlas**. The repository and internal docs still use
**Financial Atlas** where renaming would add churn.

> Research tool, not financial advice. Fair values, strategy returns, and paper-trading balances are
> model outputs based on stated assumptions and delayed/free data.

## What Works Today

- **Company research**: overview, price/volume charts, financial statements, cash-flow analysis,
  valuation, ownership, filings, peer/compare views, news/analyst surfaces, and market context.
- **Valuation engine**: DCF, owner earnings, multiples, dividend-discount, bull/base/bear scenarios,
  blended fair value, margin of safety, editable assumptions, and valuation history.
- **Screener and watchlists**: multi-criteria local-universe screening, universe warming, watchlist
  tracking, live price versus fair value, upside, and margin of safety.
- **Paper trading**: seeded strategy catalog, strategy CRUD/clone/validation, trader accounts,
  allocation/rebalance flows, and account performance/value endpoints.
- **Backtesting**: active-universe screening, point-in-time membership support, factor tests,
  parameter sweeps, and documented caveats for free-data limitations.
- **Research assistant**: assistant sessions with confirmed tool actions for local Atlas workflows
  when `OPENAI_API_KEY` is configured.
- **Hosted app controls**: login/session auth, edit gates, assistant/paper-trading rate limits, and
  Render deployment config for a private single-tenant deployment.

Deployment to **Render** is wired for one Docker web service plus managed Postgres. The container
runs the Next.js frontend on Render's public port and the FastAPI backend privately on
`127.0.0.1:8000`.

## Architecture

```
frontend/  Next.js + TypeScript + Tailwind  (UI, auth routes, /api proxy)
backend/   FastAPI + Python                  (providers -> services -> REST API)
docs/prd/  Product requirement docs           (the spec this is built from)
.scratch/  Local issue/PRD workspaces         (feature backlog and implementation notes)
```

Data flows: **providers** (SEC EDGAR, Yahoo) → **services** (normalize, cache, derive) → **REST API**
→ **UI**. Everything sits behind a pluggable provider interface, so paid sources can be added later
without a rewrite. See [docs/prd/01-architecture.md](docs/prd/01-architecture.md).

## Quick start

```bash
make setup        # backend venv + deps, frontend deps  (one time)

# then, in two terminals:
make backend      # http://127.0.0.1:8000   (FastAPI)
make frontend     # http://localhost:3000   (Next.js)
```

Open http://localhost:3000 and search a ticker (e.g. AAPL, MSFT, NVDA).

Useful local commands:

```bash
make dev          # starts backend in the background, then Next.js
make test         # backend pytest suite
cd frontend && npm run build
```

## Data sources

- **SEC EDGAR**: filings, XBRL financials, Form 4 insider transactions, and large/activist
  13D/13G ownership data. Authoritative, free, no key.
- **Yahoo Finance**: keyless EOD prices, quotes, and market data used by charts, valuation inputs,
  screeners, and simulated account marks.
- **Optional keyed providers**: FMP, Finnhub, FRED, Alpha Vantage, Twelve Data, and OpenAI can be
  enabled via environment variables. The app runs without those keys; unavailable providers
  self-disable or return explicit warnings.

Data source details live in [docs/prd/02-data-sources.md](docs/prd/02-data-sources.md).

## Deploy to Render

Use a managed Postgres database plus one Docker web service:

- Database: `financial-atlas-db`, 1 GB to start, database name `atlas`.
- Web service: `financial-atlas`, Docker runtime, Starter plan, repo root, Dockerfile `./Dockerfile`.
- Required env: `DATABASE_URL`, `BACKEND_URL=http://127.0.0.1:8000`, `SEC_USER_AGENT`,
  `AUTH_USERNAME`, `AUTH_PASSWORD`, and `AUTH_SECRET`.
- Recommended cache disk env: `CACHE_DIR=/var/data/cache`, `CACHE_MAX_MB=512`,
  `CACHE_MIN_FREE_MB=128`. The free-space reserve protects the database and price
  store that share the Render disk.
- Optional env: `OPENAI_API_KEY`, `FMP_API_KEY`, `FINNHUB_API_KEY`, `FRED_API_KEY`, and other
  provider keys documented in `backend/.env.example`.

[infra/render.yaml](infra/render.yaml) documents the same settings for review, but manual provisioning
is fine. See [docs/prd/30-deployment-render.md](docs/prd/30-deployment-render.md).

## Tests

```bash
make test
cd frontend && npm run build
```

## Known limitations / future work

- **Backtests are simulated research**, not execution-grade trading. They use documented fill
  assumptions, delayed/free data, and no brokerage integration.
- **Long-window backtests can still carry data-history bias** when free source coverage is incomplete.
  Shorter windows are more credible than claims over 10-20 years.
- **Institutional 13F holder-by-holder breakdown** is not reconstructed. It requires reverse-indexing
  every institution's 13F by CUSIP, which is heavy and unreliable on free tiers. Large/activist
  13D/13G stakes are shown.
- **News, macro, and assistant features** depend on optional provider keys and degrade with warnings
  when those providers are not configured.
- Quarterly XBRL Q4 figures can be sparse (companies often report Q4 only inside the annual 10-K).
