"""Durable daily price store (PRD free-data-pipeline).

One compact JSON row per ticker (``price_series`` table) holding the full ascending
history of **dividend/split-adjusted** daily closes. Reads are served locally; the
network is touched only for the part of the window the store doesn't have yet:

* no row              → one full-window provider fetch, then persisted forever
* need earlier bars   → one full refetch (rare: a backtest asks before stored start)
* need newer bars     → a tiny tail fetch from the last stored date

Adjusted closes are *back-adjusted*: a new split or dividend shifts the entire
historical series. Every tail merge therefore re-checks the overlap region — if the
provider's values for already-stored dates have drifted, the whole series is refetched
once instead of silently mixing two adjustment bases.

This is what keeps the platform free: a 20-year S&P-500-wide backtest costs zero
provider calls once warmed, and the nightly warm job appends one small request per
ticker per day (well inside Yahoo/Stooq tolerance).
"""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta

from ..db import PriceSeries, session_scope
from . import prices

logger = logging.getLogger(__name__)

# Overlap bars compared on every tail merge; > _READJUST_TOLERANCE relative drift on any
# of them means the provider re-based its adjusted series (split/dividend) → full refetch.
_OVERLAP_BARS = 5
_READJUST_TOLERANCE = 0.005


def _iso(d: date | str) -> str:
    return d.isoformat() if isinstance(d, date) else str(d)[:10]


def _bars_to_arrays(payload: dict) -> tuple[list[str], list[float]]:
    """Compact ascending (dates, adjusted_closes) from a price_window payload.
    Prefers adjusted_close (Yahoo adjclose; Stooq closes are already split-adjusted)."""
    rows = sorted(
        ((str(b["date"])[:10], float(b.get("adjusted_close") if b.get("adjusted_close") is not None else b["close"]))
         for b in payload["bars"] if (b.get("adjusted_close") is not None or b.get("close") is not None)),
        key=lambda r: r[0],
    )
    return [r[0] for r in rows], [r[1] for r in rows]


def _fetch(ticker: str, start: date, end: date) -> tuple[list[str], list[float], str]:
    payload, served_by = prices.price_window(ticker, start=start, end=end, interval="1d")
    dates, closes = _bars_to_arrays(payload)
    return dates, closes, served_by


def _read(ticker: str) -> dict | None:
    with session_scope() as s:
        row = s.get(PriceSeries, ticker)
        if row is None or not row.points_json:
            return None
        try:
            points = json.loads(row.points_json)
        except (TypeError, ValueError):
            return None
        dates, closes = points.get("dates") or [], points.get("closes") or []
        if not dates or len(dates) != len(closes):
            return None
        return {"dates": dates, "closes": closes, "source": row.source or "store"}


def _write(ticker: str, dates: list[str], closes: list[float], source: str) -> None:
    if not dates:
        return
    payload = json.dumps({"dates": dates, "closes": closes}, separators=(",", ":"))
    try:
        with session_scope() as s:
            row = s.get(PriceSeries, ticker)
            if row is None:
                s.add(PriceSeries(ticker=ticker, start_date=dates[0], end_date=dates[-1],
                                  points_json=payload, source=source))
            else:
                row.start_date, row.end_date = dates[0], dates[-1]
                row.points_json, row.source = payload, source
    except Exception:  # noqa: BLE001 — persisting is best-effort; serving the data matters more
        logger.warning("price store write failed for %s", ticker, exc_info=True)


def _overlap_matches(stored_dates: list[str], stored_closes: list[float],
                     fresh_dates: list[str], fresh_closes: list[float]) -> bool:
    fresh_by_date = dict(zip(fresh_dates, fresh_closes))
    checked = 0
    for i in range(len(stored_dates) - 1, -1, -1):
        fresh = fresh_by_date.get(stored_dates[i])
        if fresh is None:
            continue
        stored = stored_closes[i]
        if fresh and abs(stored - fresh) / abs(fresh) > _READJUST_TOLERANCE:
            return False
        checked += 1
        if checked >= _OVERLAP_BARS:
            break
    return True


def _slice(dates: list[str], closes: list[float], start: date, end: date) -> tuple[list[str], list[float]]:
    s_iso, e_iso = _iso(start), _iso(end)
    out_d, out_c = [], []
    for d, c in zip(dates, closes):
        if s_iso <= d <= e_iso:
            out_d.append(d)
            out_c.append(c)
    return out_d, out_c


def get_series(ticker: str, start: date, end: date) -> tuple[list[str], list[float], str]:
    """Ascending (dates, adjusted_closes, served_by) for [start, end].

    Raises only when the store is empty *and* the provider fetch fails — once a ticker
    is stored, provider outages degrade to serving the stored history.
    """
    tk = ticker.strip().upper()
    stored = _read(tk)

    if stored is None:
        dates, closes, source = _fetch(tk, start, end)
        _write(tk, dates, closes, source)
        return dates, closes, source

    dates, closes = stored["dates"], stored["closes"]

    # Need history before what we have → one full refetch covering the union.
    if _iso(start) < dates[0]:
        try:
            full_end = max(end, date.fromisoformat(dates[-1]))
            f_dates, f_closes, source = _fetch(tk, start, full_end)
            if f_dates:
                _write(tk, f_dates, f_closes, source)
                dates, closes = f_dates, f_closes
        except Exception:  # noqa: BLE001 — serve what we have
            logger.info("price store backfill failed for %s; serving stored range", tk)

    # Need bars after what we have → tail fetch with an overlap re-adjustment check.
    if _iso(end) > dates[-1]:
        try:
            tail_start = date.fromisoformat(dates[-1]) - timedelta(days=14)
            t_dates, t_closes, source = _fetch(tk, tail_start, end)
            if t_dates:
                if _overlap_matches(dates, closes, t_dates, t_closes):
                    last = dates[-1]
                    add = [(d, c) for d, c in zip(t_dates, t_closes) if d > last]
                    if add:
                        dates = dates + [d for d, _ in add]
                        closes = closes + [c for _, c in add]
                        _write(tk, dates, closes, source)
                else:
                    # Provider re-based its adjusted series (split/dividend) — replace wholesale.
                    f_dates, f_closes, source = _fetch(tk, date.fromisoformat(dates[0]), end)
                    if f_dates:
                        dates, closes = f_dates, f_closes
                        _write(tk, dates, closes, source)
        except Exception:  # noqa: BLE001 — stale tail beats a failed request
            logger.info("price store tail refresh failed for %s; serving stored bars", tk)

    out_d, out_c = _slice(dates, closes, start, end)
    return out_d, out_c, "store"


def warm(ticker: str, start: date, end: date) -> bool:
    """Ensure [start, end] is stored. True if the ticker has any bars afterwards."""
    try:
        dates, _, _ = get_series(ticker, start, end)
        return bool(dates)
    except Exception:  # noqa: BLE001
        return False


def coverage(ticker: str) -> dict | None:
    """{"start", "end", "bars"} for a stored ticker, or None."""
    stored = _read(ticker.strip().upper())
    if not stored:
        return None
    return {"start": stored["dates"][0], "end": stored["dates"][-1], "bars": len(stored["dates"])}
