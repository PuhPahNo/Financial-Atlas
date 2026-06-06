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
    def _pw(sym, *, start, end, interval="1d"):
        bars = [b for b in series_by_sym.get(sym, []) if start.isoformat() <= b["date"] <= end.isoformat()]
        return {"bars": bars, "currency": "USD"}, "stub"
    return _pw


def test_real_backtest_routes_through_active_screening_with_universe_caveat(monkeypatch):
    """Real (non-fixture) backtests route through the active S&P 500 screener and carry the
    survivorship caveat. Point-in-time entry is the expected default, so it is not flagged."""
    start, end, hist0 = date(2020, 1, 1), date(2021, 12, 31), date(2018, 1, 1)
    import app.backtesting.screen as s
    import app.backtesting.engine as eng
    series = {"AAA": _daily(hist0, end, lambda d: 100.0), "SPY": _daily(hist0, end, lambda d: 100.0)}
    monkeypatch.setattr(s.prices, "price_window", _stub_prices(series))
    monkeypatch.setattr(eng.univ, "investable_superset", lambda: ["AAA"])   # avoid network fetches
    monkeypatch.setattr(eng.univ, "members_on", lambda d: {"AAA"})

    res = eng.run_backtest(strategy={"category": "short_term", "name": "Z", "parameters": {"tickers": ["AAA"]}},
                           tickers=["AAA"], start_date=start, end_date=end, starting_cash=10000.0)
    assert any("survivorship" in w.lower() for w in res["warnings"])
    assert not any("look-ahead" in w.lower() for w in res["warnings"])
