# 18 — SEC Filings Explorer

> Parent: [00-master-prd.md](00-master-prd.md) · A browsable, searchable window into a company's
> primary documents.

## 1. Purpose / why

Let users browse a company's SEC filings, jump to the source document behind any number, follow an
8-K event timeline, and run full-text search across filings — the primary-document backbone other
modules link into.

## 2. User stories & acceptance criteria

- *As a user,* I browse filings filtered by type. **AC:** list of 10-K/10-Q/8-K/DEF 14A/4/13F with
  date, period, and a link to the primary document on EDGAR.
- *As a user,* I scan material events. **AC:** 8-K timeline with decoded item codes (e.g. 2.02 results,
  5.02 officer change).
- *As a user,* I search filing text. **AC:** full-text search returns matching filings (optionally
  scoped to a ticker).

## 3. Scope (in / out)

- **In:** filings index, type filters, 8-K item decoding, full-text search (EDGAR EFTS proxy), deep
  links from financials/insiders/institutions to source filings.
- **Out:** rendering/annotating full documents in-app (link out to EDGAR for v1).

## 4. Data requirements & sources

- Endpoints: `GET /api/v1/filings/{ticker}?forms=&limit=`, `GET /api/v1/filings/search?q=&ticker=`
  ([04](04-api-contract.md)).
- Source: **SEC EDGAR** `submissions` (index) + **EFTS full-text search**; stored in `filings`
  ([03](03-data-model.md)); refreshed daily ([05](05-caching-and-jobs.md)).

## 5. Contracts

- Index response: `{ filings:[{form_type, filing_date, period_of_report, accession_no, primary_doc_url,
  items}] }` sorted date desc. Search response: matching filings with snippets.
- **Precondition:** ticker→CIK resolvable (index) / non-empty query (search). **Postcondition:** every
  filing has a working `primary_doc_url`; 8-K `items` decoded to labels.

## 6. UI/UX

- `DataTable` of filings with type filter chips + an 8-K event `TrendChart`/timeline; search box with
  results + snippets. Links open EDGAR in a new tab (external link safety: show full URL).

## 7. Business logic

- 8-K **item-code decoding** map (1.01, 2.02, 5.02, 7.01, 8.01, ...).
- Other modules link here by `accession_no` so "source filing" is one consistent destination (DRY).

## 8. Dependencies

[02](02-data-sources.md), [03](03-data-model.md), [04](04-api-contract.md), [05](05-caching-and-jobs.md);
linked from [12](12-financial-statements.md), [16](16-insider-trading.md), [17](17-institutional-ownership.md).

## 9. Edge cases & error handling

- EFTS rate limits → cache + limiter ([05](05-caching-and-jobs.md)); empty results clearly stated.
- Very old filings (pre-XBRL) → index still shown; structured data may be unavailable (flagged).

## 10. Testing requirements

- `submissions` parsing + 8-K item decoding unit tests; search proxy contract test; link-validity test
  (primary_doc_url resolves).

## 11. Open questions & assumptions

- In-app document rendering deferred; **assume** external EDGAR links for v1.

## 12. Done criteria

- Filings index with type filters, decoded 8-K timeline, and full-text search render from EDGAR, with
  consistent source-filing deep links from other modules.
