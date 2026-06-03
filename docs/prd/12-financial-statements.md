# 12 — Financial Statement Pages

> Parent: [00-master-prd.md](00-master-prd.md)

## 1. Purpose / why

Present the three core statements (income, balance sheet, cash flow) in clean, period-columned tables
with annual/quarterly toggles and trend visuals — sourced authoritatively from SEC XBRL — so users can
read a company's financial history quickly and trust the numbers.

## 2. User stories & acceptance criteria

- *As a user,* I view income / balance / cash-flow statements with multiple years and quarters. **AC:**
  routes render period columns; annual/quarter toggle works; ≥5 years where available.
- *As a user,* I see growth/margins trends. **AC:** key lines (revenue, net income, margins) show a
  `TrendChart` and YoY % change.
- *As a user,* I know which values are reported vs computed. **AC:** derived rows carry a raw/derived
  badge ([03 §6](03-data-model.md)).

## 3. Scope (in / out)

- **In:** three statement tables, annual/quarter toggle, trend charts, YoY growth, common-size
  (% of revenue) toggle, CSV export.
- **Out:** the deep FCF analytics (lives in [13](13-cash-flow-analysis.md)); valuation ([14](14-valuation-engine.md)).

## 4. Data requirements & sources

- Endpoints: `GET /api/v1/financials/{ticker}/{income|balance-sheet|cash-flow}?period=&limit=`
  ([04](04-api-contract.md)).
- Source: **SEC EDGAR XBRL** (companyfacts) → FMP → Finnhub ([02 fallback](02-data-sources.md)).
- Fields per the statement tables in [03](03-data-model.md).

## 5. Contracts

- Response: `{ statements: [ {fiscal_year, period, ...fields, source, filing_ref} ], currency }`,
  sorted period desc.
- **Precondition:** valid `period`. **Postcondition:** consistent field set across periods (missing →
  `null`), currency stamped, each row traceable to a filing.

## 6. UI/UX

- `FinancialTable` ([06](06-design-system-ui.md)): line items as rows, periods as columns, sticky
  header/first column, raw/derived badges, link from a period to its source filing ([18](18-sec-filings-explorer.md)).
- Toggles: annual/quarter, common-size (% revenue), # periods. `TrendChart` for selected lines.
- CSV export of the visible table.

## 7. Business logic

- YoY/QoQ growth and common-size computed client-side from returned values; margins per Glossary.
- Quarterly vs TTM: provide a TTM column for income/cash-flow where quarters available.

## 8. Dependencies

[04](04-api-contract.md), [02](02-data-sources.md), [03](03-data-model.md), [06](06-design-system-ui.md),
[13](13-cash-flow-analysis.md) (shares cash-flow data), [18](18-sec-filings-explorer.md) (filing links).

## 9. Edge cases & error handling

- XBRL tag variation across filers → normalization map ([02 §9](02-data-sources.md)); unmapped line →
  shown under "Other" with the raw tag in a tooltip, never dropped silently.
- Restatements → latest filing wins; prior values available on hover.
- Banks/financials → some lines N/A; layout adapts (no negative-CapEx assumptions).

## 10. Testing requirements

- Normalization unit tests across ≥3 filers; common-size/growth math tests; API contract test;
  component test for null handling and raw/derived badge; e2e renders all three statements.

## 11. Open questions & assumptions

- TTM construction: **assume** sum of last 4 quarters for flow statements; balance sheet uses latest.

## 12. Done criteria

- All three statements render annual+quarterly from EDGAR XBRL with trends, common-size, and filing
  links. Feeds [13](13-cash-flow-analysis.md).
