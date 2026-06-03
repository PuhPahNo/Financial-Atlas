"""Yahoo Finance provider (PRD 02 §5) — keyless price history & quote.

Used as the price source since EDGAR does not provide market prices and the
keyed free APIs require sign-up. Flagged best-effort per PRD 02; sits behind the
same interface so it can be swapped for a keyed/paid source later.
"""
from __future__ import annotations

from datetime import datetime, timezone

from ..core import cache
from ..core.errors import ProviderError
from ..core.http import get_json
from .base import Capability, Interval, PriceBar, Quote

_HEADERS = {"User-Agent": "Mozilla/5.0 (Financial Atlas research tool)"}
_RANGE_MAP = {"1m": "1mo", "3m": "3mo", "6m": "6mo", "1y": "1y", "3y": "5y", "5y": "5y", "max": "max"}


class YahooProvider:
    name = "yahoo"
    capabilities = frozenset({Capability.PRICES})

    def _chart(self, ticker: str, *, yrange: str, interval: str) -> dict:
        # Yahoo uses hyphens for share classes (BRK-B); accept dotted input too.
        sym = ticker.upper().replace(".", "-")
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"

        def load():
            return get_json(url, headers=_HEADERS, params={"range": yrange, "interval": interval}, provider=self.name)

        # EOD prices change ~once/day; cache for the trading day (PRD 05 TTL table).
        ttl = 3600 if interval == "1d" else 6 * 3600
        return cache.get_or_set("yahoo", f"chart:{sym}:{yrange}:{interval}", ttl_seconds=ttl, loader=load).value

    def _chart_window(self, ticker: str, *, period1: int, period2: int, interval: str) -> dict:
        """Explicit date-window fetch — Yahoo serves true daily bars for any window
        (the ``range=max`` shortcut downsamples to monthly for long spans)."""
        sym = ticker.upper().replace(".", "-")
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"

        def load():
            return get_json(
                url, headers=_HEADERS,
                params={"period1": period1, "period2": period2, "interval": interval},
                provider=self.name,
            )

        ttl = 6 * 3600  # historical windows are immutable; cache longer
        return cache.get_or_set("yahoo", f"chart:{sym}:{period1}-{period2}:{interval}", ttl_seconds=ttl, loader=load).value

    @staticmethod
    def _parse_result(result: dict | None, ticker: str) -> list[PriceBar]:
        if not result:
            raise ProviderError(f"Yahoo returned no chart data for {ticker}")
        timestamps = result.get("timestamp") or []
        quote = (result.get("indicators", {}).get("quote") or [{}])[0]
        adj = (result.get("indicators", {}).get("adjclose") or [{}])
        adjclose = adj[0].get("adjclose") if adj else None

        bars: list[PriceBar] = []
        for i, ts in enumerate(timestamps):
            d = datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
            bars.append(PriceBar(
                date=d,
                open=_at(quote.get("open"), i),
                high=_at(quote.get("high"), i),
                low=_at(quote.get("low"), i),
                close=_at(quote.get("close"), i),
                adjusted_close=_at(adjclose, i),
                volume=int(v) if (v := _at(quote.get("volume"), i)) is not None else None,
            ))
        return [b for b in bars if b.close is not None]

    def get_price_history(self, ticker: str, *, range: str = "1y", interval: Interval = Interval.DAY) -> list[PriceBar]:
        yrange = _RANGE_MAP.get(range, "1y")
        data = self._chart(ticker, yrange=yrange, interval=interval.value if isinstance(interval, Interval) else interval)
        return self._parse_result((data.get("chart", {}).get("result") or [None])[0], ticker)

    def get_price_window(self, ticker: str, *, period1: int, period2: int, interval: Interval = Interval.DAY) -> list[PriceBar]:
        iv = interval.value if isinstance(interval, Interval) else interval
        data = self._chart_window(ticker, period1=period1, period2=period2, interval=iv)
        return self._parse_result((data.get("chart", {}).get("result") or [None])[0], ticker)

    def get_quote(self, ticker: str) -> Quote:
        # Short window so the "previous close" is the prior session, not a year ago.
        data = self._chart(ticker, yrange="5d", interval="1d")
        result = (data.get("chart", {}).get("result") or [None])[0]
        if not result:
            raise ProviderError(f"Yahoo returned no quote for {ticker}")
        meta = result.get("meta", {})
        closes = [c for c in ((result.get("indicators", {}).get("quote") or [{}])[0].get("close") or []) if c is not None]
        price = meta.get("regularMarketPrice") or (closes[-1] if closes else None)
        # Daily change = latest session vs the prior session. The second-to-last
        # daily close is the reliable "previous close"; Yahoo's chartPreviousClose
        # is the close from *before* the window, which would overstate the change.
        if len(closes) >= 2:
            prev = closes[-2]
        else:
            prev = meta.get("previousClose") or meta.get("chartPreviousClose")
        change_abs = (price - prev) if (price is not None and prev is not None) else None
        change_pct = (change_abs / prev) if (change_abs is not None and prev) else None
        vols = [v for v in ((result.get("indicators", {}).get("quote") or [{}])[0].get("volume") or []) if v is not None]
        volume = meta.get("regularMarketVolume") or (vols[-1] if vols else None)
        return Quote(
            price=price,
            previous_close=prev,
            change_abs=change_abs,
            change_pct=change_pct,
            week52_high=meta.get("fiftyTwoWeekHigh"),
            week52_low=meta.get("fiftyTwoWeekLow"),
            volume=int(volume) if volume is not None else None,
            currency=meta.get("currency") or "USD",
        )


def _at(seq, i):
    if seq is None or i >= len(seq):
        return None
    return seq[i]
