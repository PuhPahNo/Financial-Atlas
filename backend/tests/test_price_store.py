"""Durable price store (PRD free-data-pipeline): fetch-once, tail-append, re-adjust detection."""
from datetime import date, timedelta

import pytest

from app.db import PriceSeries, session_scope
from app.services import price_store

TICKER = "TSTORE"


@pytest.fixture(autouse=True)
def _clean_store():
    yield
    with session_scope() as s:
        s.query(PriceSeries).filter(PriceSeries.ticker == TICKER).delete(synchronize_session=False)


def _payload(start: date, end: date, price_fn, adjust=1.0):
    bars, d = [], start
    while d <= end:
        bars.append({"date": d.isoformat(), "close": float(price_fn(d)),
                     "adjusted_close": float(price_fn(d)) * adjust})
        d += timedelta(days=1)
    return {"bars": bars, "currency": "USD"}


def test_first_fetch_persists_then_serves_locally(monkeypatch):
    calls = {"n": 0}

    def pw(sym, *, start, end, interval="1d"):
        calls["n"] += 1
        return _payload(start, end, lambda d: 100.0), "yahoo"

    monkeypatch.setattr(price_store.prices, "price_window", pw)
    s, e = date(2020, 1, 1), date(2020, 3, 1)
    d1, c1, _ = price_store.get_series(TICKER, s, e)
    assert calls["n"] == 1 and len(d1) == 61
    # Second identical request must not touch the provider at all.
    d2, c2, served = price_store.get_series(TICKER, s, e)
    assert calls["n"] == 1 and served == "store" and d2 == d1 and c2 == c1


def test_uses_adjusted_close_over_raw(monkeypatch):
    monkeypatch.setattr(price_store.prices, "price_window",
                        lambda sym, *, start, end, interval="1d": (_payload(start, end, lambda d: 100.0, adjust=0.5), "yahoo"))
    _, closes, _ = price_store.get_series(TICKER, date(2020, 1, 1), date(2020, 1, 10))
    assert all(c == 50.0 for c in closes)  # adjusted (× 0.5), not the raw 100


def test_tail_append_fetches_only_missing_bars(monkeypatch):
    windows = []

    def pw(sym, *, start, end, interval="1d"):
        windows.append((start, end))
        return _payload(start, end, lambda d: 100.0), "yahoo"

    monkeypatch.setattr(price_store.prices, "price_window", pw)
    price_store.get_series(TICKER, date(2020, 1, 1), date(2020, 2, 1))
    dates, _, _ = price_store.get_series(TICKER, date(2020, 1, 1), date(2020, 3, 1))
    assert dates[-1] == "2020-03-01" and dates[0] == "2020-01-01"
    # The second provider call started near the stored end (overlap window), not at Jan 1.
    assert len(windows) == 2 and windows[1][0] >= date(2020, 1, 15)


def test_readjustment_triggers_full_refetch(monkeypatch):
    """When the provider re-bases its adjusted series (split/dividend), overlapping values
    drift and the store must replace the whole series instead of mixing bases."""
    phase = {"adjust": 1.0}

    def pw(sym, *, start, end, interval="1d"):
        return _payload(start, end, lambda d: 100.0, adjust=phase["adjust"]), "yahoo"

    monkeypatch.setattr(price_store.prices, "price_window", pw)
    price_store.get_series(TICKER, date(2020, 1, 1), date(2020, 2, 1))
    phase["adjust"] = 0.5  # 2:1-split-style re-basing of the entire history
    _, closes, _ = price_store.get_series(TICKER, date(2020, 1, 1), date(2020, 3, 1))
    assert all(abs(c - 50.0) < 1e-9 for c in closes)  # one basis throughout — no mixing


def test_provider_outage_serves_stored_history(monkeypatch):
    monkeypatch.setattr(price_store.prices, "price_window",
                        lambda sym, *, start, end, interval="1d": (_payload(start, end, lambda d: 100.0), "yahoo"))
    price_store.get_series(TICKER, date(2020, 1, 1), date(2020, 2, 1))

    def boom(sym, *, start, end, interval="1d"):
        raise RuntimeError("provider down")

    monkeypatch.setattr(price_store.prices, "price_window", boom)
    dates, closes, _ = price_store.get_series(TICKER, date(2020, 1, 1), date(2020, 3, 1))
    assert dates and dates[-1] == "2020-02-01"  # stale tail beats a failed request
