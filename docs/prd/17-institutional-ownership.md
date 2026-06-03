# 17 — Institutional Ownership (SEC 13F / 13D-G)

> Parent: [00-master-prd.md](00-master-prd.md) · Free institutional holdings from EDGAR.

## 1. Purpose / why

Show who owns the stock at scale — institutional holders from **13F** filings, plus activist/large
stakes from **13D/13G** — and how positions change quarter over quarter, to reveal smart-money flows.

## 2. User stories & acceptance criteria

- *As a user,* I see top institutional holders and their position sizes. **AC:** a table of holders
  with shares, value, % of their portfolio, and QoQ change.
- *As a user,* I see ownership trend and notable moves. **AC:** total institutional ownership trend +
  largest increases/decreases highlighted.
- *As a user,* I see activist/large stakes. **AC:** 13D/13G filers flagged with stake % and intent
  (13D=active, 13G=passive).

## 3. Scope (in / out)

- **In:** 13F holder table, QoQ deltas, ownership-trend, 13D/G stake flags, top buyers/sellers.
- **Out:** insider individuals ([16](16-insider-trading.md)); fund-level portfolio pages (post-v1).

## 4. Data requirements & sources

- Endpoint: `GET /api/v1/ownership/{ticker}/institutions?as_of=` ([04](04-api-contract.md)).
- Source: **SEC EDGAR 13F-HR** (holdings, reverse-mapped to the subject security) + **SC 13D/13G**
  ([02](02-data-sources.md)); stored in `institutional_holdings` ([03](03-data-model.md)).

## 5. Contracts

- Response: `{ holders:[{holder_name, shares, value, pct_of_portfolio, change_in_shares}],
  summary:{ total_institutional_shares, holder_count, qoq_change }, large_stakes:[13D/G] }`.
- **Precondition:** report period available. **Postcondition:** `change_in_shares` computed vs prior
  report; holders sorted by value desc; each row traceable to a 13F accession.

## 6. UI/UX

- `DataTable` of holders (sortable, search), summary `MetricCard`s, `TrendChart` of total institutional
  ownership, and a flagged list of 13D/G stakes ([06](06-design-system-ui.md)).

## 7. Business logic

- **QoQ change** computed on ingest by joining consecutive `report_date`s per holder ([03](03-data-model.md)).
- 13F is **quarterly and lagged (~45 days)** — UI clearly labels the report date and the lag.
- Reverse mapping: 13F lists holdings by CUSIP/issuer → map to ticker via a CUSIP↔ticker reference.

## 8. Dependencies

[02](02-data-sources.md), [03](03-data-model.md), [04](04-api-contract.md), [05](05-caching-and-jobs.md),
[18](18-sec-filings-explorer.md).

## 9. Edge cases & error handling

- CUSIP↔ticker mapping gaps → holder shown with raw issuer name + flag; never silently dropped.
- 13F restatements/amendments → latest wins. New holder (no prior) → change = full position (labeled "new").
- Lag/staleness → always show "as of {report_date}" so users don't read it as real-time.

## 10. Testing requirements

- 13F parser + CUSIP mapping tested on real filings; QoQ-delta computation unit test (incl. new/exited
  holders); API contract test.

## 11. Open questions & assumptions

- CUSIP↔ticker reference source: **assume** a maintained mapping table seeded from EDGAR/company data;
  revisit if coverage gaps appear.

## 12. Done criteria

- Institutional holders, QoQ changes, ownership trend, and 13D/G stakes render from EDGAR data with
  clear as-of labeling.
