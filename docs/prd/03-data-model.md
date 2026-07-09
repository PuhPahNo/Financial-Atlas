# 03 — Data Model & Migrations

> Parent: [00-master-prd.md](00-master-prd.md) · Extends the original spec's schema. Reference the
> [Glossary](00-master-prd.md#7-glossary) for field meanings; do not redefine here.

## 1. Purpose / why

Define one schema that works on **SQLite (local)** and **Postgres (Render)**, cleanly separates
**raw** (as-reported) from **derived** (we-computed) data, and stores enough provenance to debug and
reproduce every value.

## 2. User stories & acceptance criteria

- *As the maintainer,* I can trace any displayed number to its source provider and filing. **AC:**
  every fact row carries `source` + `filing_ref` + `fetched_at`.
- *As the maintainer,* migrations run from one ordered revision list on SQLite and Postgres. **AC:**
  each revision is transactional, recorded once, and tested against temporary SQLite databases.
- *As a user,* derived metrics never silently overwrite reported values. **AC:** raw and derived
  live in separate tables/columns.

## 3. Scope (in / out)

- **In:** tables, keys, indexes, provenance columns, migration strategy, type-parity rules.
- **Out:** query/endpoint shapes ([04](04-api-contract.md)), cache storage ([05](05-caching-and-jobs.md)).

## 4. Conventions

- **ORM:** SQLAlchemy; **migrations:** the linear `app.migrations` runner, applied at startup after
  additive model reconciliation.
- **Type parity:** use SQLAlchemy generic types (`Numeric`, `String`, `Date`, `DateTime`,
  `JSON`/`JSONB`). Money = `Numeric(20,4)` (not float) to avoid rounding drift. `JSON` maps to TEXT on
  SQLite, JSONB on Postgres.
- **Provenance (every fact table):** `source` (provider name), `filing_ref` (accession/URL where
  applicable), `fetched_at`, `as_reported` (bool). Derived rows set `source = 'derived'`.
- **Identity:** companies keyed by `ticker` (unique) **and** `cik` (SEC identity, the durable key).
- **Periods:** `fiscal_year INTEGER`, `period TEXT CHECK(period IN ('FY','Q1','Q2','Q3','Q4'))`.

## 5. Schema

### Reference / identity
```sql
CREATE TABLE companies (
  id INTEGER PRIMARY KEY,
  ticker TEXT UNIQUE NOT NULL,
  cik TEXT UNIQUE,                      -- SEC identity (zero-padded 10 digits)
  name TEXT, sector TEXT, industry TEXT, sic_code TEXT,
  description TEXT, exchange TEXT, currency TEXT DEFAULT 'USD',
  shares_outstanding NUMERIC(20,4),     -- latest known; history in fundamentals
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Prices (raw)
```sql
CREATE TABLE price_history (
  id INTEGER PRIMARY KEY,
  ticker TEXT NOT NULL,
  date DATE NOT NULL,
  open NUMERIC(20,4), high NUMERIC(20,4), low NUMERIC(20,4),
  close NUMERIC(20,4), adjusted_close NUMERIC(20,4),
  volume BIGINT,
  source TEXT, fetched_at TIMESTAMP,
  UNIQUE(ticker, date)
);
CREATE INDEX ix_price_ticker_date ON price_history(ticker, date);
```

### Fundamentals (raw, as-reported) — extends original spec
```sql
CREATE TABLE income_statements (
  id INTEGER PRIMARY KEY, ticker TEXT NOT NULL,
  fiscal_year INTEGER, period TEXT,
  revenue NUMERIC(20,4), cost_of_revenue NUMERIC(20,4), gross_profit NUMERIC(20,4),
  operating_income NUMERIC(20,4), interest_expense NUMERIC(20,4),
  pretax_income NUMERIC(20,4), net_income NUMERIC(20,4),
  eps_basic NUMERIC(20,4), eps_diluted NUMERIC(20,4),
  weighted_average_shares NUMERIC(20,4), weighted_average_shares_diluted NUMERIC(20,4),
  ebitda NUMERIC(20,4),
  source TEXT, filing_ref TEXT, filing_date DATE, fetched_at TIMESTAMP, as_reported BOOLEAN DEFAULT 1,
  UNIQUE(ticker, fiscal_year, period, source)
);

CREATE TABLE balance_sheets (
  id INTEGER PRIMARY KEY, ticker TEXT NOT NULL,
  fiscal_year INTEGER, period TEXT,
  cash_and_equivalents NUMERIC(20,4), short_term_investments NUMERIC(20,4),
  total_current_assets NUMERIC(20,4), total_assets NUMERIC(20,4),
  total_current_liabilities NUMERIC(20,4), total_liabilities NUMERIC(20,4),
  short_term_debt NUMERIC(20,4), long_term_debt NUMERIC(20,4), total_debt NUMERIC(20,4),
  shareholder_equity NUMERIC(20,4),
  source TEXT, filing_ref TEXT, filing_date DATE, fetched_at TIMESTAMP, as_reported BOOLEAN DEFAULT 1,
  UNIQUE(ticker, fiscal_year, period, source)
);

CREATE TABLE cash_flow_statements (
  id INTEGER PRIMARY KEY, ticker TEXT NOT NULL,
  fiscal_year INTEGER, period TEXT,
  operating_cash_flow NUMERIC(20,4), capital_expenditures NUMERIC(20,4),
  free_cash_flow NUMERIC(20,4),               -- stored only if as-reported; else derived table
  depreciation_and_amortization NUMERIC(20,4), stock_based_compensation NUMERIC(20,4),
  dividends_paid NUMERIC(20,4), share_repurchases NUMERIC(20,4),
  debt_issued NUMERIC(20,4), debt_repaid NUMERIC(20,4),
  change_in_working_capital NUMERIC(20,4),
  source TEXT, filing_ref TEXT, filing_date DATE, fetched_at TIMESTAMP, as_reported BOOLEAN DEFAULT 1,
  UNIQUE(ticker, fiscal_year, period, source)
);
```

### Derived metrics (we-computed — never overwrite raw)
```sql
CREATE TABLE derived_metrics (
  id INTEGER PRIMARY KEY, ticker TEXT NOT NULL,
  fiscal_year INTEGER, period TEXT,
  metric TEXT NOT NULL,        -- 'fcf','fcf_margin','fcf_conversion','fcf_per_share',
                               -- 'capex_pct_revenue','net_debt','ev', etc. (see Glossary)
  value NUMERIC(20,6),
  inputs_json JSON,            -- the exact inputs used, for reproducibility
  computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(ticker, fiscal_year, period, metric)
);
```

### Ownership & insiders
```sql
CREATE TABLE insider_transactions (              -- from SEC Form 4
  id INTEGER PRIMARY KEY, ticker TEXT NOT NULL, cik TEXT,
  insider_name TEXT, insider_title TEXT, relationship TEXT,   -- officer/director/10% owner
  transaction_date DATE, transaction_code TEXT,               -- P=buy, S=sell, etc.
  shares NUMERIC(20,4), price NUMERIC(20,4), value NUMERIC(20,4),
  shares_owned_after NUMERIC(20,4),
  filing_ref TEXT, fetched_at TIMESTAMP,
  UNIQUE(filing_ref, insider_name, transaction_date, transaction_code, shares)
);

CREATE TABLE institutional_holdings (            -- from SEC 13F (and 13D/G events)
  id INTEGER PRIMARY KEY, ticker TEXT NOT NULL,
  holder_name TEXT, holder_cik TEXT,
  report_date DATE,                              -- 13F period end
  shares NUMERIC(20,4), value NUMERIC(20,4),
  pct_of_portfolio NUMERIC(12,6),
  change_in_shares NUMERIC(20,4),                -- QoQ delta (derived on ingest)
  filing_ref TEXT, fetched_at TIMESTAMP,
  UNIQUE(ticker, holder_cik, report_date)
);
```

### Filings index
```sql
CREATE TABLE filings (
  id INTEGER PRIMARY KEY, ticker TEXT NOT NULL, cik TEXT,
  form_type TEXT,                                -- 10-K, 10-Q, 8-K, DEF 14A, 4, 13F-HR, SC 13D...
  filing_date DATE, period_of_report DATE,
  accession_no TEXT UNIQUE, primary_doc_url TEXT, items TEXT,   -- 8-K item codes
  fetched_at TIMESTAMP
);
CREATE INDEX ix_filings_ticker_form ON filings(ticker, form_type, filing_date);
```

### Valuation results — extends original spec
```sql
CREATE TABLE valuation_results (
  id INTEGER PRIMARY KEY, ticker TEXT NOT NULL, valuation_date DATE NOT NULL,
  current_price NUMERIC(20,4),
  dcf_value NUMERIC(20,4), owner_earnings_value NUMERIC(20,4),
  earnings_multiple_value NUMERIC(20,4), revenue_multiple_value NUMERIC(20,4),
  ebitda_multiple_value NUMERIC(20,4), dividend_discount_value NUMERIC(20,4),
  peer_comps_value NUMERIC(20,4),
  blended_fair_value NUMERIC(20,4),
  bear_case_value NUMERIC(20,4), base_case_value NUMERIC(20,4), bull_case_value NUMERIC(20,4),
  margin_of_safety NUMERIC(12,6),
  weights_json JSON, assumptions_json JSON,      -- full inputs → reproducible
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX ix_valuation_ticker_date ON valuation_results(ticker, valuation_date);
```

### User data (watchlists)
```sql
CREATE TABLE watchlists (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, user_id TEXT DEFAULT 'local',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE watchlist_items (
  id INTEGER PRIMARY KEY, watchlist_id INTEGER NOT NULL REFERENCES watchlists(id),
  ticker TEXT NOT NULL, added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(watchlist_id, ticker)
);
```

`user_id` defaults to `'local'` now; becomes a real FK if hosted multi-tenant ([30](30-deployment-render.md)).

### Paper trading, backtests, and assistant state
```sql
CREATE TABLE trading_strategies (
  id INTEGER PRIMARY KEY,
  category TEXT NOT NULL, name TEXT NOT NULL, slug TEXT UNIQUE NOT NULL,
  origin TEXT DEFAULT 'seeded', status TEXT DEFAULT 'active',
  description TEXT, history TEXT, methodology TEXT,
  parameters_json JSON, metrics_json JSON, caveats_json JSON,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE backtest_runs (
  id INTEGER PRIMARY KEY, strategy_id INTEGER REFERENCES trading_strategies(id),
  name TEXT, start_date DATE, end_date DATE, starting_cash NUMERIC(20,4),
  inputs_json JSON, metrics_json JSON, warnings_json JSON,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE backtest_trades (
  id INTEGER PRIMARY KEY, run_id INTEGER REFERENCES backtest_runs(id),
  trade_date DATE, ticker TEXT, side TEXT, quantity NUMERIC(20,6),
  price NUMERIC(20,4), value NUMERIC(20,4), reason TEXT
);

CREATE TABLE backtest_equity_points (
  id INTEGER PRIMARY KEY, run_id INTEGER REFERENCES backtest_runs(id),
  date DATE, cash NUMERIC(20,4), equity NUMERIC(20,4), benchmark_equity NUMERIC(20,4)
);

CREATE TABLE trader_accounts (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, emoji TEXT, bio TEXT,
  starting_cash NUMERIC(20,4), status TEXT DEFAULT 'active',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE account_allocations (
  id INTEGER PRIMARY KEY, account_id INTEGER REFERENCES trader_accounts(id),
  strategy_id INTEGER REFERENCES trading_strategies(id), weight NUMERIC(7,4),
  UNIQUE (account_id, strategy_id)
);

CREATE TABLE assistant_sessions (
  id INTEGER PRIMARY KEY, title TEXT, summary TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE assistant_messages (
  id INTEGER PRIMARY KEY, session_id INTEGER REFERENCES assistant_sessions(id),
  role TEXT NOT NULL, content TEXT NOT NULL, tool_calls_json JSON,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE assistant_pending_actions (
  id INTEGER PRIMARY KEY, session_id INTEGER REFERENCES assistant_sessions(id),
  action TEXT NOT NULL, payload_json JSON, status TEXT DEFAULT 'pending',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, resolved_at TIMESTAMP
);
```

## 6. Raw vs derived rule

- Reported values (incl. as-reported FCF when a company reports it) live in the statement tables with
  `as_reported = true`.
- Everything we compute (FCF when not reported, all ratios, net debt, EV) lives in `derived_metrics`
  with the exact `inputs_json` used. The API merges them; the UI labels derived values.

## 7. Migrations

- `atlas_schema_migrations` records one linear revision history.
- Additive model columns are reconciled first; explicit revisions handle backfills and removals.
- Destructive revisions validate live data before DDL and fail closed when preconditions are not met.
- SQLite migration behavior is covered by the local gate; Render startup is the current Postgres
  integration proof until a hosted Postgres CI lane is added.

## 8. Dependencies

[02-data-sources.md](02-data-sources.md) (normalized objects map onto these tables),
[04-api-contract.md](04-api-contract.md) (response shapes), [30](30-deployment-render.md) (Postgres).

## 9. Edge cases & error handling

- Same period reported by multiple sources → kept as separate rows (unique includes `source`);
  service picks per the fundamentals fallback order and records which.
- Restatements → newer filing supersedes; keep both, prefer latest `filing_date`.
- Missing diluted shares → fall back to basic, flagged in `inputs_json`.

## 10. Testing requirements

- Migration idempotence and fail-closed data guards on SQLite; production startup smoke on Postgres.
- Numeric precision test: money stored/read as `Numeric` preserves cents (no float drift).
- Provenance test: every inserted fact row has non-null `source` + `fetched_at`.

## 11. Open questions & assumptions

- Assume single-tenant (`user_id='local'`) until [30](30-deployment-render.md) decides accounts.
- Whether to store full filing text/HTML or just URLs — **assume URLs + extracted fields** to keep
  the DB small; fetch document on demand.

## 12. Done criteria

- Tracer bullet: `companies`, `price_history`, and the three statement tables migrate on SQLite and
  hold one ticker's data with provenance. → Thicken with ownership/filings/valuation tables.
