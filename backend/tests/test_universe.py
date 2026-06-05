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


def test_parse_changes_handles_iso_and_named_dates():
    csv = 'Date,Added,Removed\n2021-06-01,C,X\n"March 2, 2020",B,Y\n'
    out = universe._parse_changes(csv)
    assert {"date": "2021-06-01", "added": "C", "removed": "X"} in out
    assert {"date": "2020-03-02", "added": "B", "removed": "Y"} in out


def test_reconstruct_membership_backward():
    current = {"A", "B", "C"}
    changes = [{"date": "2020-03-01", "added": "B", "removed": "Y"},
               {"date": "2021-06-01", "added": "C", "removed": "X"}]
    assert universe.reconstruct(current, changes, date(2021, 12, 1)) == {"A", "B", "C"}  # no later changes
    assert universe.reconstruct(current, changes, date(2021, 1, 1)) == {"A", "B", "X"}   # C not yet in; X still in
    assert universe.reconstruct(current, changes, date(2019, 1, 1)) == {"A", "X", "Y"}   # before both joins


def test_members_on_uses_changelog(monkeypatch):
    monkeypatch.setattr(universe, "sp500_tickers", lambda: ["A", "B", "C"])
    monkeypatch.setattr(universe, "_changes", lambda: [{"date": "2021-06-01", "added": "C", "removed": "X"}])
    universe._members_on_iso.cache_clear()
    try:
        assert universe.members_on(date(2021, 1, 1)) == {"A", "B", "X"}
        assert universe.members_on(date(2022, 1, 1)) == {"A", "B", "C"}
    finally:
        universe._members_on_iso.cache_clear()


def test_investable_superset_includes_etfs_and_removed_names(monkeypatch):
    monkeypatch.setattr(universe, "sp500_tickers", lambda: ["A", "B"])
    monkeypatch.setattr(universe, "_changes", lambda: [{"date": "2021-06-01", "added": "B", "removed": "Z"}])
    sup = set(universe.investable_superset())
    assert {"A", "B", "Z"} <= sup          # current + a since-removed name
    assert {"SPY", "TLT", "QQQ"} <= sup    # ETFs folded in
