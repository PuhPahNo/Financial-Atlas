# 19 — News, Events & Macro

> Parent: [00-master-prd.md](00-master-prd.md) · Context layer around a company.

## 1. Purpose / why

Provide timely context — company news, upcoming earnings and dividend dates, and macro indicators
(rates, inflation) — so users interpret prices and valuations against the broader backdrop. All from
free sources.

## 2. User stories & acceptance criteria

- *As a user,* I see recent news for a ticker. **AC:** a dated news list with source + link.
- *As a user,* I see the next earnings and dividend dates. **AC:** earnings/dividend calendar entries
  when available.
- *As a user,* I see macro context. **AC:** key FRED series (10Y yield, CPI, Fed Funds) render as
  small trends.

## 3. Scope (in / out)

- **In:** company news feed, earnings/dividend calendar, macro dashboard (FRED), optional ex-div
  history.
- **Out:** sentiment scoring / NLP (post-v1); paid premium news.

## 4. Data requirements & sources

- Endpoints: `GET /api/v1/news/{ticker}`, `GET /api/v1/macro?series=` ([04](04-api-contract.md)).
- News: Tiingo → Finnhub; earnings/dividends: Finnhub/FMP where free; macro: **FRED**
  ([02](02-data-sources.md)). TTL: news 1 day, macro 1 day ([05](05-caching-and-jobs.md)).

## 5. Contracts

- News response: `{ articles:[{title, source, url, published_at}] }`. Macro response:
  `{ series:{ DGS10:[{date,value}], ... } }`.
- **Precondition:** valid ticker / known FRED series ids. **Postcondition:** articles sorted desc;
  external URLs shown in full (link safety).

## 6. UI/UX

- News list with source badges + external links (new tab, full URL shown); calendar chips for next
  earnings/dividend; macro `TrendChart` mini-panels ([06](06-design-system-ui.md)).

## 7. Business logic

- De-duplicate news by URL/title across providers. Map common FRED series ids to friendly labels.

## 8. Dependencies

[02](02-data-sources.md), [04](04-api-contract.md), [05](05-caching-and-jobs.md), [06](06-design-system-ui.md).

## 9. Edge cases & error handling

- No free news for a small-cap → graceful empty state. Earnings date unavailable on free tier → hide
  the chip rather than guess. Macro series unavailable → skip that panel.

## 10. Testing requirements

- News de-dup unit test; FRED client contract test; empty-state component test.

## 11. Open questions & assumptions

- Earnings/dividend calendar coverage varies on free tiers; **assume** best-effort, clearly labeled.

## 12. Done criteria

- Company news, available earnings/dividend dates, and a small FRED macro panel render from free
  sources with safe external links.
