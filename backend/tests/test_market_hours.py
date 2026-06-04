"""Market-hours gate (PRD live-paper-valuation). Pure function — explicit UTC instants,
no reliance on the wall clock."""
from datetime import datetime, timezone

from app.core import market_hours as m


def _utc(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def test_open_during_regular_session_edt():
    # 2026-06-04 is a Thursday; 14:00 UTC == 10:00 ET (EDT, UTC-4).
    assert m.is_market_open(_utc("2026-06-04T14:00")) is True


def test_closed_before_open_and_after_close():
    assert m.is_market_open(_utc("2026-06-04T12:00")) is False  # 08:00 ET, pre-open
    assert m.is_market_open(_utc("2026-06-04T21:00")) is False  # 17:00 ET, post-close


def test_closed_on_weekend():
    assert m.is_market_open(_utc("2026-06-06T14:00")) is False  # Saturday


def test_closed_on_holiday():
    # 2026-07-03 is the observed Independence Day market closure.
    assert m.is_market_open(_utc("2026-07-03T14:00")) is False


def test_open_boundaries_in_winter_est():
    # January -> EST (UTC-5); 14:30 UTC == 09:30 ET (open), 14:29 == 09:29 (closed).
    assert m.is_market_open(_utc("2026-01-02T14:30")) is True
    assert m.is_market_open(_utc("2026-01-02T14:29")) is False


def test_last_trading_day_skips_weekend():
    assert m.last_trading_day(_utc("2026-06-07T12:00")).isoformat() == "2026-06-05"  # Sun -> Fri


def test_last_trading_day_skips_holiday():
    # 2026-07-04 (Sat) -> back past the 07-03 holiday to Thu 07-02.
    assert m.last_trading_day(_utc("2026-07-04T12:00")).isoformat() == "2026-07-02"
