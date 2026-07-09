# 02 — Data Sources & Provider Contracts

> Parent: [00-master-prd.md](00-master-prd.md) · The reversibility backbone: external sources
> normalize into common domain models and explicit fallback chains.

## 1. Purpose / why

Catalog the **free** data sources, define normalized provider contracts (so sources are swappable
and testable), specify **fallback chains** per data domain, and document which **paid**
APIs would add value with their **monthly cost** — for the user to approve case-by-case, never
adopted silently.

## 2. User stories & acceptance criteria

- *As the maintainer,* I can add a source by implementing the relevant normalized methods and adding
  it to a registry chain. **AC:** no UI edits are required.
- *As a user,* a page still loads if the primary source is down or rate-limited. **AC:** fallback
  chain returns data from the next capable provider; the response notes which provider served it.
- *As the user (owner),* I can see exactly what a paid upgrade would buy and cost. **AC:** the
  premium appendix lists value prop + approx $/mo + whether a free workaround exists.

## 3. Scope (in / out)

- **In:** provider contracts, domain chains, free source catalog, fallback policy, attribution,
  premium appendix.
- **Out:** caching/rate-limit mechanics ([05](05-caching-and-jobs.md)), persistence ([03](03-data-model.md)).

## 4. Provider contracts (Design by Contract)

A provider is an adapter for **one** source. It returns **normalized domain objects** (defined in
[03](03-data-model.md)); it never returns raw upstream JSON to services. There is no speculative
monolithic `ProviderProtocol` or capability enum. Each adapter implements only the methods it can
serve, while `providers/registry.py` defines ordered chains per domain and invokes the requested
method when present.

```python
CHAINS = {
    "profile": [sec_edgar],
    "prices": [yahoo, stooq],
    "quote": [yahoo, fmp, stooq],
    "income": [sec_edgar],
    # ...
}

result, served_by = run_chain("prices", "get_price_history", ticker, ...)
```

**Contract (applies to implemented methods):**
- **Preconditions:** `ticker` is non-empty, upper-cased, resolvable to a CIK/identifier; date ranges
  satisfy `start ≤ end`.
- **Postconditions:** returns a list (possibly empty) of **schema-valid** normalized objects sorted
  deterministically (prices by date asc; statements by fiscal period desc); monetary fields carry an
  explicit `currency`; never returns partially-populated raw dicts.
- **Invariants:** adapters do not write application tables. Provider HTTP responses may use the
  shared bounded cache so quotas and fallback behavior remain centralized.
- **Errors:** raises `RateLimitError`, `NotFoundError`, or `ProviderError` (never returns `None`/`{}`
  to signal failure).

## 5. Free source catalog

> ⚠️ Rate limits and free-tier terms change frequently. Treat the numbers below as *design-time
> estimates*; the implementer must re-verify against each provider's current docs and record the
> live values in `core/config.py`.

| Source | Free capabilities | Approx free limit | Auth | Notes |
| --- | --- | --- | --- | --- |
| **SEC EDGAR** | filings, income/balance/cashflow (XBRL), insider (Form 4), institutional (13F/13D-G), profile (CIK/SIC) | ~10 req/s fair-use; no daily cap | None (descriptive `User-Agent` w/ contact email **required**) | **Primary source.** Authoritative, unlimited-ish, no key. Ticker→CIK via `company_tickers.json`. |
| **FRED** (St. Louis Fed) | macro series (rates, CPI, GDP) | generous (~120 req/min) | Free API key | For macro context module. |
| **Financial Modeling Prep** | movers, quotes, peers, analyst price targets | small daily cap (verify) | Free API key | Optional enrichment; guarded by a daily budget. |
| **Alpha Vantage** | prices (EOD/intraday), some fundamentals | ~25 req/day (verify) | Free API key | Very low cap → use sparingly, cache hard. |
| **Twelve Data** | prices, quotes | ~800 req/day, ~8 req/min | Free API key | Good EOD/price workhorse within caps. |
| **Finnhub** | quotes, company news, recommendations, peers | ~60 req/min | Free API key | Optional research enrichment. |
| **Tiingo** | EOD prices, news | ~1k req/day, limited unique symbols/mo | Free API key | Clean EOD history + news. |
| **Stooq** | EOD prices (CSV) | unmetered, best-effort | None | Keyless fallback for price history. |

Implemented today: SEC EDGAR, Yahoo, Stooq, FMP (movers/quotes/peers/price targets), and Finnhub
(quotes/news/recommendations/peers). The other rows are candidate sources, not installed adapters.

**Unofficial (evaluate before use):** Yahoo Finance via `yfinance` is free and broad but ToS is a
gray area and the endpoint is unstable. **Decision:** not part of the sanctioned backbone; may be
added behind the same interface as a *best-effort* fallback only after a ToS/reliability review,
clearly flagged. EDGAR + the keyed free APIs above are the reliable core.

## 6. Fallback chains (per data domain)

Ordered by trust then quota. The service tries providers in order, skipping disabled/rate-limited
ones, and stamps `served_by` on the result.

| Domain | Chain |
| --- | --- |
| Fundamentals (income/balance/cashflow) | **SEC EDGAR (XBRL)** → FMP → Finnhub |
| Company profile | SEC EDGAR (CIK/SIC) → FMP → Finnhub |
| Price history (EOD) | Twelve Data → Tiingo → Stooq → Alpha Vantage |
| Real-time-ish quote | Finnhub → Twelve Data |
| Insider transactions | **SEC EDGAR (Form 4)** → Finnhub |
| Institutional holdings | **SEC EDGAR (13F / 13D-G)** |
| Filings & full-text search | **SEC EDGAR** |
| News | Tiingo → Finnhub |
| Macro | **FRED** |

EDGAR is authoritative for anything it covers; third-party APIs are convenience/cross-check layers,
not the source of truth for financials.

## 7. Attribution & compliance

- EDGAR requires a descriptive `User-Agent` including contact email — set once in the EDGAR provider.
- Respect each provider's rate limits via the central limiter ([05](05-caching-and-jobs.md)).
- Surface "Data: SEC EDGAR / FMP / …" attribution in the UI footer where required by terms.

## 8. Dependencies

[03-data-model.md](03-data-model.md) (normalized object shapes), [05-caching-and-jobs.md](05-caching-and-jobs.md)
(limiter + cache), [01-architecture.md](01-architecture.md) (provider layer).

## 9. Edge cases & error handling

- All providers for a domain exhausted/rate-limited → service returns cached (possibly stale) data
  flagged `stale: true`, or a typed `503`-style error if no cache.
- EDGAR XBRL tag variations across companies → normalization map with a tested fallback tag list.
- Ticker not resolvable to CIK → `NotFoundError` surfaced as 404.

## 10. Testing requirements

- **Contract tests** run against *every* provider using recorded fixtures (VCR-style): each must
  satisfy the postconditions (sorted, schema-valid, currency-stamped).
- Fallback engine test: primary raises `RateLimitError` → next capable provider serves; `served_by`
  reflects it.
- EDGAR XBRL normalization tested against ≥3 real companies with differing tag usage.

## 11. Open questions & assumptions

- Implemented adapters are SEC EDGAR, Yahoo, Stooq, FMP, and Finnhub. FRED, Alpha Vantage, and
  Twelve Data remain future options and have no runtime configuration today.
- Re-verify all free-tier limits at implementation time (they drift).

## 12. Done criteria

- Tracer bullet: EDGAR provider implemented + contract-tested, serving profile + fundamentals for one
  ticker. → Thicken by adding price + fallback providers.

---

## Appendix A — Premium upgrade candidates (NOT adopted without approval)

> Free coverage is strong for fundamentals, filings, insider, and institutional data (all via EDGAR).
> The real free-tier gaps are **price-history depth/frequency**, **real-time quotes**, **options**,
> and **convenient pre-parsed fundamentals at scale**. Pricing is **approximate — verify before
> purchase**; each entry says what it unlocks and the free workaround.

| Candidate | Approx $/mo | What it unlocks vs free | Free workaround |
| --- | --- | --- | --- |
| **Polygon.io — Stocks Starter** | ~$29 | Years of EOD + intraday history, aggregates, broad symbol coverage, generous limits | Stooq/Twelve Data EOD with smaller history + tight caps |
| **Financial Modeling Prep — paid** | ~$22–29 | Higher daily caps, deeper history, ratios/metrics pre-computed | EDGAR XBRL (we compute ratios ourselves) |
| **Tiingo — paid** | ~$10–50 | More symbols, higher limits, better news | Free Tiingo tier + Stooq |
| **Alpha Vantage — premium** | ~$50 | 75+ req/min, removes the painful free cap | Avoid relying on AV; use Twelve Data/Tiingo |
| **Nasdaq Data Link / Intrinio** | varies (often $50+) | Curated datasets, alt-data, standardized fundamentals | EDGAR + our normalization |
| **Options data (e.g. Polygon Options)** | ~$29+ add-on | Options chains/flow (out of v1 scope) | None free & reliable — defer |

**Recommendation:** ship entirely free. If/when price-history depth becomes the bottleneck for
charts/backtesting, the single highest-value upgrade is **Polygon Starter (~$29/mo)** — and because
it sits behind `ProviderProtocol`, adopting it is a registration change, not a refactor.
