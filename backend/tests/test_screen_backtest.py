"""Routing: real (non-fixture, non-rule) backtests go through the active S&P 500 screener.

The point-in-time / no-look-ahead, all-cash, and fundamental-gate behaviors are covered in
test_active_backtest.py (the active engine is the only screening path now)."""
from datetime import date, timedelta


def _daily(start, end, price_fn):
    out, d = [], start
    while d <= end:
        out.append({"date": d.isoformat(), "close": float(price_fn(d))})
        d += timedelta(days=1)
    return out


def _stub_prices(series_by_sym):
    def _gs(sym, start, end):
        bars = [b for b in series_by_sym.get(sym, []) if start.isoformat() <= b["date"] <= end.isoformat()]
        return [b["date"] for b in bars], [float(b["close"]) for b in bars], "stub"
    return _gs


def test_real_backtest_routes_through_active_screening_with_integrity_report(monkeypatch):
    """Real (non-fixture) backtests route through the active S&P 500 screener. With
    point-in-time membership on (the default), the survivorship caveat is replaced by the
    integrity report: membership passes, delisted-coverage stays an honest warning."""
    start, end, hist0 = date(2020, 1, 1), date(2021, 12, 31), date(2018, 1, 1)
    import app.backtesting.screen as s
    import app.backtesting.engine as eng
    series = {"AAA": _daily(hist0, end, lambda d: 100.0), "SPY": _daily(hist0, end, lambda d: 100.0)}
    monkeypatch.setattr(s.price_store, "get_series", _stub_prices(series))
    monkeypatch.setattr(eng.univ, "investable_superset", lambda: ["AAA"])   # avoid network fetches
    monkeypatch.setattr(eng.univ, "members_on", lambda d: {"AAA"})
    monkeypatch.setattr(eng.univ, "membership_available", lambda: True)  # change-log loadable

    res = eng.run_backtest(strategy={"category": "short_term", "name": "Z", "parameters": {"tickers": ["AAA"]}},
                           tickers=["AAA"], start_date=start, end_date=end, starting_cash=10000.0)
    checks = {c["id"]: c["status"] for c in res["integrity"]["checks"]}
    assert checks["membership"] == "pass"        # PIT membership reconstruction active
    assert checks["delistings"] == "warn"        # residual survivorship disclosed honestly
    assert checks["adjusted_prices"] == "pass"
    assert checks["execution"] == "pass"
    assert not any("survivorship" in w.lower() for w in res["warnings"])
    assert not any("look-ahead" in w.lower() for w in res["warnings"])


def test_membership_degrades_to_warn_when_changelog_unavailable(monkeypatch):
    """If the S&P change-log can't be loaded, the run must DISCLOSE that it screened
    today's survivors (membership warn + universe caveat) — never grade itself pass."""
    start, end, hist0 = date(2020, 1, 1), date(2021, 12, 31), date(2018, 1, 1)
    import app.backtesting.screen as s
    import app.backtesting.engine as eng
    series = {"AAA": _daily(hist0, end, lambda d: 100.0), "SPY": _daily(hist0, end, lambda d: 100.0)}
    monkeypatch.setattr(s.price_store, "get_series", _stub_prices(series))
    monkeypatch.setattr(eng.univ, "investable_superset", lambda: ["AAA"])
    monkeypatch.setattr(eng.univ, "membership_available", lambda: False)  # change-log outage

    res = eng.run_backtest(strategy={"category": "short_term", "name": "Z", "parameters": {"tickers": ["AAA"]}},
                           tickers=["AAA"], start_date=start, end_date=end, starting_cash=10000.0)
    checks = {c["id"]: c["status"] for c in res["integrity"]["checks"]}
    assert checks["membership"] == "warn"
    assert any("survivorship" in w.lower() for w in res["warnings"])


def test_index_models_need_no_tickers(monkeypatch):
    """Index-scanning models (Piotroski, Magic Formula, …) declare no tickers of their
    own — they must route to the active screener, not fail 'at least one ticker'."""
    start, end, hist0 = date(2020, 1, 1), date(2021, 12, 31), date(2018, 1, 1)
    import app.backtesting.screen as s
    import app.backtesting.engine as eng
    rise = lambda d: 50 + 50 * ((d - hist0).days / (end - hist0).days)
    series = {"AAA": _daily(hist0, end, rise), "SPY": _daily(hist0, end, lambda d: 100.0)}
    monkeypatch.setattr(s.price_store, "get_series", _stub_prices(series))
    monkeypatch.setattr(eng.univ, "investable_superset", lambda: ["AAA"])
    monkeypatch.setattr(eng.univ, "members_on", lambda d: {"AAA"})

    res = eng.run_backtest(
        strategy={"category": "short_term", "name": "Mom", "parameters": {"model": "momentum_12_1", "tickers": []}},
        tickers=[], start_date=start, end_date=end, starting_cash=10000.0)
    assert res["integrity"]["checks"]  # routed through the active screener, not an error


def test_fixed_basket_models_trade_only_their_tickers(monkeypatch):
    """A model declaring universe=tickers (e.g. ETF rotation) trades only its own basket —
    the S&P superset is never scanned and the integrity report marks the fixed universe."""
    start, end, hist0 = date(2020, 1, 1), date(2021, 12, 31), date(2018, 1, 1)
    import app.backtesting.screen as s
    import app.backtesting.engine as eng
    rise = lambda d: 50 + 50 * ((d - hist0).days / (end - hist0).days)
    series = {"SPY": _daily(hist0, end, rise), "AGG": _daily(hist0, end, lambda d: 100.0)}
    monkeypatch.setattr(s.price_store, "get_series", _stub_prices(series))
    monkeypatch.setattr(eng.univ, "investable_superset", lambda: (_ for _ in ()).throw(AssertionError("superset must not be scanned")))

    res = eng.run_backtest(
        strategy={"category": "risk_rotation", "name": "GEM",
                  "parameters": {"tickers": ["SPY", "AGG"], "universe": "tickers", "model": "dual_momentum",
                                 "lookback_days": 252, "take_profit_pct": 0.99, "stop_loss_pct": 0.99}},
        tickers=["SPY", "AGG"], start_date=start, end_date=end, starting_cash=10000.0)
    traded = {t["ticker"] for t in res["trades"]}
    assert traded <= {"SPY", "AGG"}
    checks = {c["id"]: c["status"] for c in res["integrity"]["checks"]}
    assert checks["membership"] == "info"  # fixed basket — index membership does not apply
