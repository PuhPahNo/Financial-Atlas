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
    # The engine reads prices through the durable price store; tests stub the store's
    # get_series so nothing touches the network or persists synthetic bars to the DB.
    def gs(sym, start, end):
        bars = [b for b in series.get(sym, []) if start.isoformat() <= b["date"] <= end.isoformat()]
        return [b["date"] for b in bars], [float(b["close"]) for b in bars], "stub"
    return gs


def _sells(res):
    return [t for t in res["trades"] if t["side"] in ("sell", "cover")]


def test_enters_after_uptrend_then_takes_profit(monkeypatch):
    start, end, h0, turn = date(2020, 1, 1), date(2021, 12, 31), date(2018, 1, 1), date(2020, 6, 30)

    def price(d):
        if d <= turn:
            return 100 - 45 * ((d - h0).days / (turn - h0).days)   # decline
        return 55 + 150 * ((d - turn).days / (end - turn).days)    # strong rise -> +25% TP

    monkeypatch.setattr(screen.price_store, "get_series",
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

    monkeypatch.setattr(screen.price_store, "get_series",
                        _stub({"STP": _daily(h0, end, price), "SPY": _daily(h0, end, lambda d: 100.0)}))
    res = run_active_backtest(
        strategy={"category": "short_term", "name": "S", "parameters": {"take_profit_pct": 0.99}},
        universe=["STP"], start_date=start, end_date=end, starting_cash=10000.0)
    assert any("stop-loss" in t["reason"] for t in _sells(res))


def test_max_hold_fires(monkeypatch):
    start, end, h0 = date(2020, 1, 1), date(2020, 6, 30), date(2018, 1, 1)
    price = lambda d: 50 + 10 * ((d - h0).days / (end - h0).days)   # gentle steady uptrend
    monkeypatch.setattr(screen.price_store, "get_series",
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
    monkeypatch.setattr(screen.price_store, "get_series", _stub(series))
    res = run_active_backtest(
        strategy={"category": "short_term", "name": "N",
                  "parameters": {"max_positions": 2, "take_profit_pct": 0.99, "stop_loss_pct": 0.99}},
        universe=[f"T{i}" for i in range(5)], start_date=start, end_date=end, starting_cash=10000.0)
    assert len(res["final_holdings"]) <= 2


def test_membership_blocks_nonmembers_before_join_date(monkeypatch):
    """A name that qualifies technically is still not bought until it's an index member."""
    start, end, h0 = date(2020, 1, 1), date(2021, 12, 31), date(2018, 1, 1)
    rise = lambda d: 50 + 50 * ((d - h0).days / (end - h0).days)   # steady uptrend; both qualify
    monkeypatch.setattr(screen.price_store, "get_series",
                        _stub({"OLD": _daily(h0, end, rise), "NEW": _daily(h0, end, rise),
                               "SPY": _daily(h0, end, lambda d: 100.0)}))

    def membership(d):  # NEW only joins the index on 2021-01-01
        return {"OLD", "NEW"} if d >= date(2021, 1, 1) else {"OLD"}

    res = run_active_backtest(
        strategy={"category": "short_term", "name": "M",
                  "parameters": {"max_positions": 5, "take_profit_pct": 0.99, "stop_loss_pct": 0.99}},
        universe=["OLD", "NEW"], start_date=start, end_date=end, starting_cash=10000.0,
        membership_on=membership)
    new_buys = [t for t in res["trades"] if t["side"] == "buy" and t["ticker"] == "NEW"]
    old_buys = [t for t in res["trades"] if t["side"] == "buy" and t["ticker"] == "OLD"]
    assert new_buys and all(t["date"] >= date(2021, 1, 1) for t in new_buys)  # not bought pre-membership
    assert old_buys and any(t["date"] < date(2021, 1, 1) for t in old_buys)   # OLD bought earlier


def test_dead_ticker_is_skiplisted_and_not_refetched(monkeypatch):
    """A symbol that hard-errors is remembered, so the next backtest doesn't re-fetch it."""
    start, end, h0 = date(2020, 1, 1), date(2021, 12, 31), date(2018, 1, 1)
    rise = lambda d: 50 + 50 * ((d - h0).days / (end - h0).days)
    live = _daily(h0, end, rise)
    calls = {"DEAD": 0}

    def gs(sym, start, end):
        if sym == "DEAD":
            calls["DEAD"] += 1
            raise RuntimeError("404 — delisted")
        bars = [b for b in {"LIVE": live, "SPY": _daily(h0, end, lambda d: 100.0)}.get(sym, [])
                if start.isoformat() <= b["date"] <= end.isoformat()]
        return [b["date"] for b in bars], [float(b["close"]) for b in bars], "stub"

    store: dict = {}
    monkeypatch.setattr(screen.cache, "peek", lambda ns, k, ttl: store.get((ns, k)))
    monkeypatch.setattr(screen.cache, "put", lambda ns, k, v: store.__setitem__((ns, k), v))
    monkeypatch.setattr(screen.price_store, "get_series", gs)

    strat = {"category": "short_term", "name": "X", "parameters": {"take_profit_pct": 0.99, "stop_loss_pct": 0.99}}
    screen.run_active_backtest(strategy=strat, universe=["LIVE", "DEAD"], start_date=start, end_date=end, starting_cash=10000.0)
    assert calls["DEAD"] == 1 and store.get(("dead_ticker", "DEAD")) is True  # errored once, now skiplisted
    screen.run_active_backtest(strategy=strat, universe=["LIVE", "DEAD"], start_date=start, end_date=end, starting_cash=10000.0)
    assert calls["DEAD"] == 1  # second run skipped it entirely — no re-fetch


def test_all_cash_when_nothing_qualifies(monkeypatch):
    start, end, h0 = date(2020, 1, 1), date(2021, 12, 31), date(2018, 1, 1)
    price = lambda d: 200 - 50 * ((d - h0).days / (end - h0).days)  # strictly declining
    monkeypatch.setattr(screen.price_store, "get_series",
                        _stub({"DWN": _daily(h0, end, price), "SPY": _daily(h0, end, lambda d: 100.0)}))
    res = run_active_backtest(strategy={"category": "short_term", "name": "C", "parameters": {}},
                              universe=["DWN"], start_date=start, end_date=end, starting_cash=10000.0)
    assert res["trades"] == []
    assert abs(res["equity_curve"][-1]["equity"] - 10000.0) < 1e-6
