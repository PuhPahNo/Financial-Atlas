"""Point-in-time screening backtest engine (PRD backtest-integrity).

Proves the look-ahead fix: a stock is only bought once the model's criteria are met at that
historical date — never on day 1 because it is a known winner."""
from datetime import date, timedelta

from app.backtesting import screen
from app.backtesting.screen import run_screen_backtest


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


def test_no_day1_buy_enters_only_after_uptrend(monkeypatch):
    start, end, hist0, turn = date(2020, 1, 1), date(2021, 12, 31), date(2018, 1, 1), date(2020, 6, 30)

    def price(d):
        if d <= turn:  # decline 100 -> 55
            return 100 - 45 * ((d - hist0).days / (turn - hist0).days)
        return 55 + 95 * ((d - turn).days / (end - turn).days)  # rise 55 -> 150

    series = {"MOM": _daily(hist0, end, price), "SPY": _daily(hist0, end, lambda d: 100.0)}
    monkeypatch.setattr(screen.prices, "price_window", _stub_prices(series))

    res = run_screen_backtest(
        strategy={"category": "short_term", "name": "Mom", "parameters": {"tickers": ["MOM"]}},
        tickers=["MOM"], start_date=start, end_date=end, starting_cash=10000.0,
    )
    buys = [t for t in res["trades"] if t["side"] == "buy"]
    assert buys, "should eventually buy once momentum turns up"
    # Crucially: NO buy on day 1 or anywhere during the decline.
    assert all(t["date"] > turn for t in buys)
    assert res["equity_curve"][-1]["equity"] > 10000.0  # rode the legitimate uptrend


def test_all_cash_when_nothing_qualifies(monkeypatch):
    start, end, hist0 = date(2020, 1, 1), date(2021, 12, 31), date(2018, 1, 1)
    price = lambda d: 200 - 50 * ((d - hist0).days / (end - hist0).days)  # strictly declining
    series = {"DWN": _daily(hist0, end, price), "SPY": _daily(hist0, end, lambda d: 100.0)}
    monkeypatch.setattr(screen.prices, "price_window", _stub_prices(series))

    res = run_screen_backtest(
        strategy={"category": "short_term", "name": "Dn", "parameters": {"tickers": ["DWN"]}},
        tickers=["DWN"], start_date=start, end_date=end, starting_cash=10000.0,
    )
    assert res["trades"] == []
    assert abs(res["equity_curve"][-1]["equity"] - 10000.0) < 1e-6
    assert res["metrics"]["total_return"] == 0.0


def test_fundamental_gate_waits_for_filing(monkeypatch):
    start, end, hist0 = date(2020, 1, 1), date(2021, 12, 31), date(2018, 1, 1)
    series = {"FUN": _daily(hist0, end, lambda d: 100.0), "SPY": _daily(hist0, end, lambda d: 100.0)}
    monkeypatch.setattr(screen.prices, "price_window", _stub_prices(series))

    def fake_as_of(ticker, d):  # fundamentals only "known" from 2021 onward
        if d < date(2021, 1, 1):
            return None
        return {"fcf": 100.0, "fcf_margin": 0.3, "net_debt_to_fcf": 0.5, "shares": 1000.0,
                "dividends_paid": 0.0, "revenue": 333.0}
    monkeypatch.setattr(screen, "as_of", fake_as_of)

    res = run_screen_backtest(
        strategy={"category": "long_term", "name": "Val", "parameters": {"tickers": ["FUN"]}},
        tickers=["FUN"], start_date=start, end_date=end, starting_cash=10000.0,
    )
    buys = [t for t in res["trades"] if t["side"] == "buy"]
    assert buys, "should buy once fundamentals qualify"
    assert all(t["date"] >= date(2021, 1, 1) for t in buys)  # never before the filing was known


def test_real_backtest_routes_through_screening_with_caveats():
    """The no-look-ahead caveats are attached to real (non-fixture) screening results."""
    start, end, hist0 = date(2020, 1, 1), date(2021, 12, 31), date(2018, 1, 1)
    import app.backtesting.screen as s
    series = {"AAA": _daily(hist0, end, lambda d: 100.0), "SPY": _daily(hist0, end, lambda d: 100.0)}
    orig = s.prices.price_window
    s.prices.price_window = _stub_prices(series)
    try:
        from app.backtesting.engine import run_backtest
        res = run_backtest(strategy={"category": "short_term", "name": "Z", "parameters": {"tickers": ["AAA"]}},
                           tickers=["AAA"], start_date=start, end_date=end, starting_cash=10000.0)
    finally:
        s.prices.price_window = orig
    assert any("no look-ahead" in w.lower() for w in res["warnings"])
    assert any("survivorship" in w.lower() for w in res["warnings"])
