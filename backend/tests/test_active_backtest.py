"""Active S&P 500 screening engine (PRD active-sp500-screening).

Synthetic, deterministic proofs that the engine scans, enters point-in-time, and exits on
take-profit / stop-loss / max-hold, holding at most top-N."""
from datetime import date, timedelta

from app.backtesting import screen
from app.backtesting.screen import run_active_backtest


def _daily(start, end, f):
    out, d = [], start
    while d <= end:
        out.append({"date": d.isoformat(), "close": float(f(d))})
        d += timedelta(days=1)
    return out


def _stub(series):
    def pw(sym, *, start, end, interval="1d"):
        return {"bars": [b for b in series.get(sym, []) if start.isoformat() <= b["date"] <= end.isoformat()],
                "currency": "USD"}, "stub"
    return pw


def _sells(res):
    return [t for t in res["trades"] if t["side"] in ("sell", "cover")]


def test_enters_after_uptrend_then_takes_profit(monkeypatch):
    start, end, h0, turn = date(2020, 1, 1), date(2021, 12, 31), date(2018, 1, 1), date(2020, 6, 30)

    def price(d):
        if d <= turn:
            return 100 - 45 * ((d - h0).days / (turn - h0).days)   # decline
        return 55 + 150 * ((d - turn).days / (end - turn).days)    # strong rise -> +25% TP

    monkeypatch.setattr(screen.prices, "price_window",
                        _stub({"MOM": _daily(h0, end, price), "SPY": _daily(h0, end, lambda d: 100.0)}))
    res = run_active_backtest(strategy={"category": "short_term", "name": "M", "parameters": {}},
                              universe=["MOM"], start_date=start, end_date=end, starting_cash=10000.0)
    buys = [t for t in res["trades"] if t["side"] == "buy"]
    assert buys and all(t["date"] > turn for t in buys)            # no day-1 buy; only after uptrend
    assert any("take-profit" in t["reason"] for t in _sells(res))


def test_stop_loss_fires(monkeypatch):
    start, end, h0 = date(2020, 1, 1), date(2020, 12, 31), date(2018, 1, 1)

    def price(d):  # long flat-low base, jump to 100 at the open, then decline immediately
        if d < date(2020, 1, 1):
            return 50.0  # keeps SMA100 far below entry, so a 12% drop fires before any SMA cross
        return max(40.0, 100.0 - 0.5 * (d - date(2020, 1, 1)).days)

    monkeypatch.setattr(screen.prices, "price_window",
                        _stub({"STP": _daily(h0, end, price), "SPY": _daily(h0, end, lambda d: 100.0)}))
    res = run_active_backtest(
        strategy={"category": "short_term", "name": "S", "parameters": {"take_profit_pct": 0.99}},
        universe=["STP"], start_date=start, end_date=end, starting_cash=10000.0)
    assert any("stop-loss" in t["reason"] for t in _sells(res))


def test_max_hold_fires(monkeypatch):
    start, end, h0 = date(2020, 1, 1), date(2020, 6, 30), date(2018, 1, 1)
    price = lambda d: 50 + 10 * ((d - h0).days / (end - h0).days)   # gentle steady uptrend
    monkeypatch.setattr(screen.prices, "price_window",
                        _stub({"SLW": _daily(h0, end, price), "SPY": _daily(h0, end, lambda d: 100.0)}))
    res = run_active_backtest(
        strategy={"category": "short_term", "name": "H",
                  "parameters": {"take_profit_pct": 0.99, "stop_loss_pct": 0.99, "max_hold_days": 30}},
        universe=["SLW"], start_date=start, end_date=end, starting_cash=10000.0)
    assert any("max-hold" in t["reason"] for t in _sells(res))


def test_never_holds_more_than_top_n(monkeypatch):
    start, end, h0 = date(2020, 1, 1), date(2021, 12, 31), date(2018, 1, 1)
    series = {f"T{i}": _daily(h0, end, lambda d, i=i: 50 + (20 + i) * ((d - h0).days / (end - h0).days))
              for i in range(5)}
    series["SPY"] = _daily(h0, end, lambda d: 100.0)
    monkeypatch.setattr(screen.prices, "price_window", _stub(series))
    res = run_active_backtest(
        strategy={"category": "short_term", "name": "N",
                  "parameters": {"max_positions": 2, "take_profit_pct": 0.99, "stop_loss_pct": 0.99}},
        universe=[f"T{i}" for i in range(5)], start_date=start, end_date=end, starting_cash=10000.0)
    assert len(res["final_holdings"]) <= 2


def test_all_cash_when_nothing_qualifies(monkeypatch):
    start, end, h0 = date(2020, 1, 1), date(2021, 12, 31), date(2018, 1, 1)
    price = lambda d: 200 - 50 * ((d - h0).days / (end - h0).days)  # strictly declining
    monkeypatch.setattr(screen.prices, "price_window",
                        _stub({"DWN": _daily(h0, end, price), "SPY": _daily(h0, end, lambda d: 100.0)}))
    res = run_active_backtest(strategy={"category": "short_term", "name": "C", "parameters": {}},
                              universe=["DWN"], start_date=start, end_date=end, starting_cash=10000.0)
    assert res["trades"] == []
    assert abs(res["equity_curve"][-1]["equity"] - 10000.0) < 1e-6
