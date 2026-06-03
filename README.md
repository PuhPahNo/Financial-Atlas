# Financial Atlas

A high-end, local-first stock analysis & valuation platform — Koyfin/Finviz-class research built
entirely on **free public data** (SEC EDGAR + Yahoo Finance), with **no API keys required**.

> Research tool — not financial advice. All fair values are model outputs based on stated assumptions.

## What works today (Phases 1–7)

- **Company Overview** — profile + key metrics (market cap, P/E, Price/FCF, EV/EBITDA, dividend yield,
  net debt, 52-wk range) from live data.
- **Price & Volume Charts** — candlesticks + volume (TradingView Lightweight Charts), range/interval toggles.
- **Financial Statements** — income / balance / cash-flow, annual & quarterly, straight from SEC XBRL.
- **Cash Flow Analysis** — FCF trends, FCF Margin %, FCF Conversion %, FCF/Share, CapEx % Revenue,
  buybacks, dividends, debt issuance/repayment, capital-returns — the full quality picture.
- **Valuation Engine** — 6 models (DCF, Owner Earnings, Earnings/Revenue/EBITDA multiples, Dividend
  Discount), bull/base/bear scenarios, blended fair value, margin of safety, **editable assumptions**.
- **Ownership** — insider transactions parsed from SEC **Form 4** (net buy/sell, cluster detection) +
  large/activist stakes from **13D/13G**.
- **Filings** — browsable SEC filings with form filters and decoded **8-K item codes**, linking to EDGAR.
- **Screener** — multi-criteria filters (FCF margin, P/E, MoS, …) over the locally-ingested dataset.
- **Watchlists** — track tickers with live price vs blended fair value, upside, and margin of safety.

Deployment to **Render** is wired as a Blueprint ([infra/render.yaml](infra/render.yaml)) — Postgres +
API + web + a daily refresh cron — ready to deploy when you connect your Render account.

## Architecture

```
frontend/  Next.js + TypeScript + Tailwind  (UI; proxies /api -> backend)
backend/   FastAPI + Python                  (providers -> services -> REST API)
docs/prd/  Product requirement docs           (the spec this is built from)
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

## Data sources

- **SEC EDGAR** — filings, XBRL financials, (planned) insider Form 4 & institutional 13F. Authoritative, free, no key.
- **Yahoo Finance** — keyless EOD prices & quotes.
- Free keyed providers (FMP, Twelve Data, Finnhub, FRED) and paid upgrade options are documented in
  [docs/prd/02-data-sources.md](docs/prd/02-data-sources.md) and slot in behind the same interface.

## Deploy to Render

Push this repo to GitHub, then in Render: **New → Blueprint → select the repo**. Render reads
[infra/render.yaml](infra/render.yaml) and provisions Postgres, the API, the web app, and a daily
refresh cron. After the first deploy, set `SEC_USER_AGENT` (your contact email) in the dashboard.
See [docs/prd/30-deployment-render.md](docs/prd/30-deployment-render.md).

## Tests

```bash
cd backend && ./.venv/bin/python -m pytest -q   # valuation engine suite (10 tests)
```

## Known limitations / future work

- **Institutional 13F holder-by-holder** breakdown is not reconstructed (it requires reverse-indexing
  every institution's 13F by CUSIP — heavy & unreliable on free tiers). Large/activist 13D/13G stakes
  *are* shown.
- **News & macro (FRED)** providers are stubbed behind the interface; they activate when free API
  keys are supplied.
- Quarterly XBRL Q4 figures can be sparse (companies often report Q4 only inside the annual 10-K).
