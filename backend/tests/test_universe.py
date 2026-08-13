"""S&P 500 universe sourcing + point-in-time membership (PRD active-sp500-screening, pit-membership)."""
from datetime import date

from app.backtesting import universe


def test_parse_csv_normalizes_symbols():
    text = "Symbol,Security,Sector\nAAPL,Apple,Tech\nBRK.B,Berkshire,Fin\n\n"
    assert universe._parse_csv(text) == ["AAPL", "BRK-B"]


def test_falls_back_to_bundled_list_when_fetch_fails(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("offline")
    monkeypatch.setattr(universe, "get_text", boom)
    out = universe.sp500_tickers()
    assert len(out) >= 100 and "AAPL" in out  # bundled large-cap fallback, non-empty


def test_parse_membership_handles_open_and_closed_stints():
    csv = ("ticker,start_date,end_date\n"
           "AAPL,1996-01-02,\n"
           "AAL,1996-01-02,1997-01-15\n"
           "AAL,2015-03-23,2024-09-23\n"
           "BRK.B,2010-02-16,\n")
    out = universe._parse_membership(csv)
    assert {"ticker": "AAPL", "start": "1996-01-02", "end": None} in out
    assert {"ticker": "AAL", "start": "1996-01-02", "end": "1997-01-15"} in out
    assert {"ticker": "AAL", "start": "2015-03-23", "end": "2024-09-23"} in out
    assert {"ticker": "BRK-B", "start": "2010-02-16", "end": None} in out  # symbol normalized


def test_members_on_uses_stint_intervals(monkeypatch):
    stints = [
        {"ticker": "A", "start": "1996-01-02", "end": None},
        {"ticker": "C", "start": "2021-06-01", "end": None},
        {"ticker": "X", "start": "2000-01-01", "end": "2021-05-31"},
        {"ticker": "R", "start": "1996-01-02", "end": "2005-01-01"},   # re-added later
        {"ticker": "R", "start": "2020-01-01", "end": None},
    ]
    monkeypatch.setattr(universe, "_membership", lambda: stints)
    universe._members_on_iso.cache_clear()
    try:
        assert universe.members_on(date(2021, 1, 1)) == {"A", "X", "R"}   # before C joined; X still in
        assert universe.members_on(date(2022, 1, 1)) == {"A", "C", "R"}   # X removed, C added
        assert universe.members_on(date(2010, 1, 1)) == {"A", "X"}        # R between its two stints
    finally:
        universe._members_on_iso.cache_clear()


def test_members_on_degrades_without_memoizing(monkeypatch):
    monkeypatch.setattr(universe, "sp500_tickers", lambda: ["A", "B"])
    monkeypatch.setattr(universe, "_membership", lambda: None)
    universe._members_on_iso.cache_clear()
    try:
        assert universe.membership_available() is False
        assert universe.members_on(date(2021, 1, 1)) == {"A", "B"}  # degraded fallback
        # Recovery: once the source is back, the same date must reflect real data —
        # the degraded answer must not have been memoized.
        monkeypatch.setattr(universe, "_membership", lambda: [{"ticker": "Z", "start": "1996-01-02", "end": None}])
        assert universe.members_on(date(2021, 1, 1)) == {"Z"}
    finally:
        universe._members_on_iso.cache_clear()


def test_investable_superset_includes_etfs_and_removed_names(monkeypatch):
    monkeypatch.setattr(universe, "sp500_tickers", lambda: ["A", "B"])
    monkeypatch.setattr(universe, "_membership", lambda: [
        {"ticker": "B", "start": "2021-06-01", "end": None},
        {"ticker": "Z", "start": "2000-01-01", "end": "2021-06-01"},
    ])
    sup = set(universe.investable_superset())
    assert {"A", "B", "Z"} <= sup          # current + a since-removed name
    assert {"SPY", "TLT", "QQQ"} <= sup    # ETFs folded in


def test_investable_between_excludes_stints_outside_requested_window(monkeypatch):
    monkeypatch.setattr(universe, "_membership", lambda: [
        {"ticker": "OLD", "start": "2000-01-01", "end": "2010-12-31"},
        {"ticker": "LEFT", "start": "2020-01-01", "end": "2023-06-30"},
        {"ticker": "JOINED", "start": "2024-02-01", "end": None},
        {"ticker": "FUTURE", "start": "2027-01-01", "end": None},
    ])

    names = set(universe.investable_between(date(2023, 1, 1), date(2026, 1, 1)))

    assert {"LEFT", "JOINED", "SPY", "QQQ"} <= names
    assert {"OLD", "FUTURE"}.isdisjoint(names)


def test_investable_between_degrades_to_current_names(monkeypatch):
    monkeypatch.setattr(universe, "_membership", lambda: None)
    monkeypatch.setattr(universe, "sp500_tickers", lambda: ["A", "B"])

    names = set(universe.investable_between(date(2020, 1, 1), date(2021, 1, 1)))

    assert {"A", "B", "SPY"} <= names


def test_membership_between_captures_only_relevant_stints_without_daily_retention(monkeypatch):
    calls = []
    monkeypatch.setattr(universe, "_membership", lambda: calls.append("load") or [
        {"ticker": "OLD", "start": "2000-01-01", "end": "2010-12-31"},
        {"ticker": "LEFT", "start": "2020-01-01", "end": "2023-06-30"},
        {"ticker": "JOINED", "start": "2024-02-01", "end": None},
    ])

    resolver = universe.membership_between(
        date(2023, 1, 1), date(2026, 1, 1), extra={"SPY"},
    )

    assert calls == ["load"]
    assert resolver(date(2023, 3, 1)) == {"LEFT", "SPY"}
    assert resolver(date(2025, 3, 1)) == {"JOINED", "SPY"}
    assert calls == ["load"]  # no cache-file reparse for each simulation day
    assert universe._members_on_iso.cache_info().maxsize == 8
