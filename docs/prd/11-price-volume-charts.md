# 11 — Price & Volume Charts

> Parent: [00-master-prd.md](00-master-prd.md)

## 1. Purpose / why

Provide a fast, readable price chart with volume and basic technical overlays so users can see trend,
volatility, and volume context alongside the fundamental/valuation views.

## 2. User stories & acceptance criteria

- *As a user,* I see a candlestick chart with volume and can switch timeframe. **AC:** daily/weekly/
  monthly toggle and range presets (1m–max) re-query and redraw.
- *As a user,* I can add moving averages. **AC:** 50/200-period SMA overlays toggle on/off.
- *As a user,* volume aligns with price. **AC:** volume bars share the x-axis and crosshair with price.

## 3. Scope (in / out)

- **In:** candlestick + volume, timeframe/range toggles, SMA(50/200) and optional EMA/RSI, crosshair
  tooltip, source badge.
- **Out:** intraday/real-time tick, options, drawing tools (post-v1).

## 4. Data requirements & sources

- Endpoint: `GET /api/v1/prices/{ticker}?range=&interval=` ([04](04-api-contract.md)).
- Price chain: Twelve Data → Tiingo → Stooq → Alpha Vantage ([02](02-data-sources.md)). EOD bars
  cached until next close ([05 TTL](05-caching-and-jobs.md)).

## 5. Contracts

- Response: `{ bars: [{date,open,high,low,close,adjusted_close,volume}], currency }`, sorted date asc.
- **Precondition:** valid `range`/`interval` enum. **Postcondition:** contiguous trading-day bars
  (gaps preserved, not zero-filled); indicators computed client-side from `adjusted_close`.

## 6. UI/UX

- `StockChart` (TradingView Lightweight Charts) + synced `VolumeChart` ([06](06-design-system-ui.md)).
- Toolbar: range presets, interval toggle, indicator toggles, source badge.
- Crosshair tooltip shows OHLCV + date; legend shows active indicators.

## 7. Business logic

- SMA/EMA/RSI computed in `lib/` (pure, unit-tested) from adjusted closes; window configurable.
- Weekly/monthly aggregation from daily bars when the provider lacks the interval (documented).

## 8. Dependencies

[04](04-api-contract.md), [02](02-data-sources.md), [05](05-caching-and-jobs.md), [06](06-design-system-ui.md).

## 9. Edge cases & error handling

- Thin history (recent IPO) → render available range, disable longer presets with tooltip.
- Splits/dividends → prefer `adjusted_close` for indicators; show raw close in tooltip.
- Provider gap day → leave gap; never interpolate.

## 10. Testing requirements

- Indicator unit tests (SMA/EMA/RSI vs hand-computed series).
- Aggregation test (daily→weekly) preserves OHLC semantics.
- Component test: range/interval change triggers refetch; e2e smoke renders chart for a ticker.

## 11. Open questions & assumptions

- Indicator set v1: **assume** SMA50/200 + RSI14; EMA and more in a later pass.

## 12. Done criteria

- Candlestick + volume + range/interval toggles render from live cached data; SMA overlays work.
