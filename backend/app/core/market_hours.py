"""US equity market-hours gate (PRD live-paper-valuation).

Pure, dependency-free: Eastern time is derived from explicit US DST rules so the slim
production container needs no ``tzdata``/``zoneinfo``/``pytz``. The regular session is
Mon–Fri 09:30–16:00 ET, minus the hardcoded NYSE full-day holidays below. Half-day early
closes are treated as full sessions — good enough for gating a ~15-min-delayed mark.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

# NYSE full-day closures, 2024–2027 (ISO dates). Extend as the calendar is published.
_HOLIDAYS: frozenset[str] = frozenset({
    # 2024
    "2024-01-01", "2024-01-15", "2024-02-19", "2024-03-29", "2024-05-27",
    "2024-06-19", "2024-07-04", "2024-09-02", "2024-11-28", "2024-12-25",
    # 2025
    "2025-01-01", "2025-01-20", "2025-02-17", "2025-04-18", "2025-05-26",
    "2025-06-19", "2025-07-04", "2025-09-01", "2025-11-27", "2025-12-25",
    # 2026
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25",
    "2026-06-19", "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25",
    # 2027
    "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31",
    "2027-06-18", "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24",
})

_OPEN_MINUTES = 9 * 60 + 30   # 09:30 ET
_CLOSE_MINUTES = 16 * 60      # 16:00 ET


def _first_sunday(year: int, month: int) -> int:
    first = date(year, month, 1)
    return 1 + (6 - first.weekday()) % 7  # weekday(): Mon=0 .. Sun=6


def _is_dst(now_utc: datetime) -> bool:
    """US DST: 2nd Sunday of March 02:00 → 1st Sunday of November 02:00 (local).
    Compared at the UTC transition instants (07:00 UTC spring-forward, 06:00 UTC fall-back)."""
    year = now_utc.year
    dst_start = datetime(year, 3, _first_sunday(year, 3) + 7, 7, 0, tzinfo=timezone.utc)
    dst_end = datetime(year, 11, _first_sunday(year, 11), 6, 0, tzinfo=timezone.utc)
    return dst_start <= now_utc < dst_end


def _eastern(now_utc: datetime | None) -> datetime:
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    elif now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    offset = 4 if _is_dst(now_utc) else 5  # EDT = UTC-4, EST = UTC-5
    return (now_utc - timedelta(hours=offset)).replace(tzinfo=None)


def is_market_open(now_utc: datetime | None = None) -> bool:
    """True during the US regular cash session (Mon–Fri 09:30–16:00 ET, non-holiday)."""
    et = _eastern(now_utc)
    if et.weekday() >= 5:
        return False
    if et.date().isoformat() in _HOLIDAYS:
        return False
    minutes = et.hour * 60 + et.minute
    return _OPEN_MINUTES <= minutes < _CLOSE_MINUTES


def last_trading_day(now_utc: datetime | None = None) -> date:
    """Most recent NYSE trading day on or before the current Eastern date."""
    d = _eastern(now_utc).date()
    while d.weekday() >= 5 or d.isoformat() in _HOLIDAYS:
        d -= timedelta(days=1)
    return d
