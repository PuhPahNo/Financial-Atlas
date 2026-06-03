# 16 — Insider Trading (SEC Form 4)

> Parent: [00-master-prd.md](00-master-prd.md) · Free, authoritative insider data straight from EDGAR.

## 1. Purpose / why

Surface insider buying/selling (officers, directors, 10% owners) from SEC **Form 4** filings, with
trends and cluster detection, so users can gauge insider conviction — all from free EDGAR data.

## 2. User stories & acceptance criteria

- *As a user,* I see recent insider transactions for a ticker. **AC:** a table of Form 4 transactions
  (insider, role, code, shares, price, value, date, shares-owned-after).
- *As a user,* I distinguish open-market buys from option/sell activity. **AC:** transaction codes
  decoded (P=open-market buy, S=sell, A/M=grants/exercises, etc.) and filterable.
- *As a user,* I see net insider sentiment and clusters. **AC:** rolling net buy/sell value + a
  "cluster buy" flag when multiple insiders buy within a window.

## 3. Scope (in / out)

- **In:** Form 4 ingestion/parsing, transaction table, code decoding, net-sentiment trend, cluster
  detection, per-insider history.
- **Out:** Form 144 (planned-sale notices) and 13D/G activist intent (the latter in [17](17-institutional-ownership.md)).

## 4. Data requirements & sources

- Endpoint: `GET /api/v1/ownership/{ticker}/insiders?since=` ([04](04-api-contract.md)).
- Source: **SEC EDGAR Form 4** (XML) via `submissions` + filing documents ([02](02-data-sources.md));
  optional Finnhub cross-check. Stored in `insider_transactions` ([03](03-data-model.md)).
- Refreshed daily by `refresh_filings` ([05](05-caching-and-jobs.md)).

## 5. Contracts

- Response: `{ transactions:[...], summary:{ net_value_30d, net_value_90d, buy_count, sell_count,
  cluster_buy: bool } }`, sorted date desc.
- **Precondition:** ticker→CIK resolvable. **Postcondition:** each transaction maps to its Form 4
  accession (`filing_ref`); codes decoded; values computed as `shares×price` when price present.

## 6. UI/UX

- `DataTable` of transactions (filter by code/role/insider) + summary `MetricCard`s (net buy/sell) +
  a `TrendChart` of net insider value over time; cluster-buy badge ([06](06-design-system-ui.md)).

## 7. Business logic

- **Transaction code decoding** map (P, S, A, M, F, G, ...). Distinguish **open-market** (P/S) from
  derivative/grant activity for an "open-market net" metric (more signal than grants).
- **Cluster buy** = ≥N distinct insiders with open-market buys within D days (configurable).

## 8. Dependencies

[02](02-data-sources.md) (EDGAR parsing), [03](03-data-model.md), [04](04-api-contract.md),
[05](05-caching-and-jobs.md), [18](18-sec-filings-explorer.md) (links to the filing).

## 9. Edge cases & error handling

- Form 4 amendments (4/A) → supersede prior; keep both, prefer latest.
- Multi-row Form 4 (several transactions in one filing) → each persisted separately (unique key in [03](03-data-model.md)).
- Missing price (gifts/grants) → value `null`, excluded from open-market net.

## 10. Testing requirements

- Form 4 XML parser tested against real filings incl. amendments and multi-transaction forms.
- Code-decoding + open-market-net + cluster-detection unit tests; API contract test.

## 11. Open questions & assumptions

- Cluster thresholds (N insiders / D days): **assume** N=3, D=30, configurable.

## 12. Done criteria

- Insider transactions render from parsed Form 4 data with decoded codes, net-sentiment trend, and
  cluster flag, linking to source filings.
