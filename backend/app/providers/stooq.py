"""Stooq provider (PRD 02) — keyless daily price history & derived quote.

A free CSV endpoint (stooq.com) used as the fallback price source when Yahoo is
unavailable (e.g. Yahoo blocking cloud/datacenter IPs). Daily resolution only and
end-of-day (delayed) prices, which is acceptable for a degraded fallback. No key;
sits behind the same provider interface as Yahoo so the chain can fail over to it.
"""
from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta, timezone

from ..core import cache
from ..core.errors import ProviderError
from ..core.http import get_text
from .base import Capability, Interval, PriceBar, Quote

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
}
_URL = "https://stooq.com/q/d/l/"
_INTERVAL = {Interval.DAY: "d", Interval.WEEK: "w", Interval.MONTH: "m"}
# Approximate calendar days per range, used to translate a range into a date window.
_RANGE_DAYS = {"1m": 31, "3m": 93, "6m": 186, "1y": 366, "3y": 1100, "5y": 1830, "max": 36500}


def _symbol(ticker: str) -> str:
    # Stooq uses hyphens for share classes and a market suffix for US listings.
    return ticker.strip().upper().replace(".", "-").lower() + ".us"


def _interval_code(interval) -> str:
    iv = interval if isinstance(interval, Interval) else Interval.DAY
    return _INTERVAL.get(iv, "d")


def _f(value: str | None) -> float | None:
    if value in (None, "", "N/D"):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _parse_csv(text: str, sym: str) -> list[PriceBar]:
    # Stooq returns "No data" (or an HTML error/throttle page) instead of a CSV
    # header when a symbol is unknown or the host is rejecting us.
    if not text or not text.lstrip().lower().startswith("date"):
        raise ProviderError(f"Stooq returned no data for {sym}")
    bars: list[PriceBar] = []
    for row in csv.DictReader(io.StringIO(text)):
        d = (row.get("Date") or "").strip()
        if not d:
            continue
        vol = _f(row.get("Volume"))
        bars.append(PriceBar(
            date=d,
            open=_f(row.get("Open")),
            high=_f(row.get("High")),
            low=_f(row.get("Low")),
            close=_f(row.get("Close")),
            # Stooq close is split-adjusted; reuse it as adjusted_close (no separate field).
            adjusted_close=_f(row.get("Close")),
            volume=int(vol) if vol is not None else None,
        ))
    return [b for b in bars if b.close is not None]


class StooqProvider:
    name = "stooq"
    capabilities = frozenset({Capability.PRICES})

    def _bars(self, sym: str, *, code: str, d1: str | None = None, d2: str | None = None) -> list[PriceBar]:
        params: dict[str, str] = {"s": sym, "i": code}
        if d1:
            params["d1"] = d1
        if d2:
            params["d2"] = d2

        def load():
            return get_text(_URL, headers=_HEADERS, params=params, provider=self.name)

        # Daily bars settle once per trading day; cache for the trading window.
        key = f"hist:{sym}:{code}:{d1 or ''}-{d2 or ''}"
        text = cache.get_or_set("stooq", key, ttl_seconds=6 * 3600, loader=load).value
        return _parse_csv(text, sym)

    def get_price_history(self, ticker: str, *, range: str = "1y", interval: Interval = Interval.DAY) -> list[PriceBar]:
        code = _interval_code(interval)
        days = _RANGE_DAYS.get(range, 366)
        d1 = None if range == "max" else (date.today() - timedelta(days=days)).strftime("%Y%m%d")
        return self._bars(_symbol(ticker), code=code, d1=d1)

    def get_price_window(self, ticker: str, *, period1: int, period2: int, interval: Interval = Interval.DAY) -> list[PriceBar]:
        d1 = datetime.fromtimestamp(period1, tz=timezone.utc).strftime("%Y%m%d")
        d2 = datetime.fromtimestamp(period2, tz=timezone.utc).strftime("%Y%m%d")
        return self._bars(_symbol(ticker), code=_interval_code(interval), d1=d1, d2=d2)

    def get_quote(self, ticker: str) -> Quote:
        # Derive a quote from ~13 months of daily bars: last close, prior session,
        # and 52-week range. Delayed (EOD) but enough to keep the UI populated.
        since = (date.today() - timedelta(days=400)).strftime("%Y%m%d")
        bars = self._bars(_symbol(ticker), code="d", d1=since)
        closes = [b.close for b in bars if b.close is not None]
        if not closes:
            raise ProviderError(f"Stooq has no quote for {ticker}")
        price = closes[-1]
        prev = closes[-2] if len(closes) >= 2 else None
        change_abs = (price - prev) if prev is not None else None
        change_pct = (change_abs / prev) if (change_abs is not None and prev) else None
        highs = [b.high for b in bars if b.high is not None]
        lows = [b.low for b in bars if b.low is not None]
        vols = [b.volume for b in bars if b.volume is not None]
        return Quote(
            price=price,
            previous_close=prev,
            change_abs=change_abs,
            change_pct=change_pct,
            week52_high=max(highs) if highs else None,
            week52_low=min(lows) if lows else None,
            volume=vols[-1] if vols else None,
            currency="USD",
        )
