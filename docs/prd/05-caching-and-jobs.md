# 05 — Caching, Rate Limits & Background Jobs

> Parent: [00-master-prd.md](00-master-prd.md) · Makes free, rate-limited sources feel fast and
> resilient.

## 1. Purpose / why

Free data sources have tight rate limits and latency. A disciplined cache + central rate limiter +
scheduled refresh jobs let the platform serve warm pages instantly, survive provider outages with
stale-but-flagged data, and stay within free quotas.

## 2. User stories & acceptance criteria

- *As a user,* a previously-viewed ticker loads instantly. **AC:** warm cache hit < 200 ms server time.
- *As the maintainer,* we never exceed a provider's documented rate limit. **AC:** the limiter blocks/
  queues calls; integration test proves no burst over the cap.
- *As a user,* I still see data during an outage, clearly marked stale. **AC:** `meta.stale=true` when
  served past TTL because upstream failed.

## 3. Scope (in / out)

- **In:** cache layers, TTL policy, rate limiter, refresh jobs, scheduling (local vs Render).
- **Out:** what each endpoint returns ([04](04-api-contract.md)), schema ([03](03-data-model.md)).

## 4. Cache layers

Two tiers, both behind `cache_service`:

1. **Response/raw cache** (provider responses) — keyed `{provider}:{method}:{ticker}:{params}`.
   Backend: bounded filesystem cache locally and on the persistent Render disk
   ([config in 01](01-architecture.md)).
2. **Persistent store** (normalized facts) — the DB itself ([03](03-data-model.md)) is the durable
   cache for fundamentals/filings/ownership. The compact `price_series` rows are also the durable
   cache for explicit historical windows, so nightly price-store refreshes bypass duplicate raw
   response files; price/quote request freshness is otherwise handled by TTL.

### TTL policy (data changes at very different rates)
| Data | TTL | Rationale |
| --- | --- | --- |
| Intraday/quote | 1–5 min | changes constantly |
| EOD prices | until next trading day close | one bar/day |
| Fundamentals (10-K/Q) | 7–30 days | changes only on new filing |
| Filings index / insider / 13F | 1 day | new filings arrive daily/quarterly |
| Company profile | 30 days | rarely changes |
| Macro (FRED) | 1 day | periodic releases |

On miss/expiry: try fallback chain ([02](02-data-sources.md)); on total failure, serve last good
value with `stale=true`.

## 5. Central rate limiter (Design by Contract)

- One limiter instance **per provider**, configured from that provider's documented limits
  (req/sec, req/min, req/day). Token-bucket; calls block or queue rather than 429.
- **Precondition:** every outbound provider call acquires a token. **Invariant:** issued calls in any
  rolling window ≤ provider cap. **Postcondition:** on upstream 429, exponential backoff + mark
  provider cooling-down so the fallback engine skips it.
- Daily-quota providers (e.g. Alpha Vantage ~25/day) tracked with a persistent counter that resets at
  the provider's reset time.

## 6. Background refresh jobs

Keep popular/watchlisted tickers warm so user requests are cache hits.

| Job | Cadence | Action |
| --- | --- | --- |
| `warm_prices` | nightly at configured UTC hour | warm adjusted prices + PIT fundamentals; deep-refresh a rotating slice |
| `refresh_headlines` | after `warm_prices` | recompute active strategy headline backtests and prune old runs |
| live account marks | about every 60s while market is open | pre-warm authenticated trader values; isolate each uncached sleeve backtest |
| queued backtest worker | continuous | launch one memory-heavy queued run at a time in a fresh child |

- Local and Render use the same FastAPI lifespan scheduler inside the single web service. Nightly
  warming runs in one disposable child, then every headline strategy runs in its own fresh child.
  The finer process boundary returns each full-universe model's allocator heap to the OS before the
  next model loads; phase-only isolation retained enough heap to exceed a 512 MB instance on the
  second strategy. It does not provision another Render service, worker, or Cron Job.
- Active screening backtests and maintenance phases share a cross-process lock, so memory-heavy
  scans queue instead of overlapping on the 512 MB service.
- Interactive synchronous/assistant backtests use a database-backed child while preserving their
  response contract. Parameter sweeps and account performance/holdings use one child per value or
  sleeve, so allocator high-water memory never transfers to the long-lived FastAPI process or the
  next simulation.
- Jobs are idempotent/best-effort and log counts fetched, skipped, and failed.

## 7. Dependencies

[02](02-data-sources.md) (providers + fallback), [03](03-data-model.md) (durable store),
[01](01-architecture.md) (cache/job config), [30](30-deployment-render.md) (Render service).

## 8. Edge cases & error handling

- Thundering herd (many requests for a cold ticker) → single-flight lock so only one provider call is
  made; others await the result. Lock entries are released when the last waiter leaves.
- Cache backend unavailable → degrade to direct provider calls (slower) without erroring.
- Repeated provider failure for a stored price series → serve the stored range and suppress redundant
  tail/deep-refresh attempts for six hours.
- Job partial failure or killed child → log the failed phase, continue the scheduler, and leave the
  web process available; correctness continues to use on-demand/stale-data fallbacks.

## 9. Testing requirements

- Rate-limiter test: simulated burst never exceeds the configured cap.
- TTL test: expired entry triggers refetch; fresh entry does not.
- Stale-fallback test: upstream failure after TTL serves last-good with `stale=true`.
- Single-flight test: N concurrent cold requests → 1 upstream call.
- Maintenance isolation test: every headline gets a distinct child, and a child killed by a signal
  reports failure while the parent continues with the remaining strategies and final pruning.

## 10. Open questions & assumptions

- Render uses the persistent disk for the response cache; revisit Key-Value only if the service
  becomes multi-instance.
- Universe size for `warm_universe` depends on the [00 open question](00-master-prd.md#11-open-questions).

## 11. Done criteria

- Tracer bullet: response cache + per-provider limiter wired into the EDGAR/price path; second request
  for a ticker is a measured cache hit. → Thicken with refresh jobs in Phase 2/5.

## 12. Pragmatic notes

- The cache + limiter are **orthogonal** to providers and services — added once, used everywhere.
- TTLs are **configuration**, not code — tuning freshness never requires a code change (reversibility).
