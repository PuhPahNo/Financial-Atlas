"""End-to-end coverage for the two active-engine paths the audit flagged as untested
(.scratch/paper-trading-audit/AUDIT.md T1/T2): the point-in-time fundamental gate and
short-direction execution accounting. Synthetic + deterministic; no network."""
from datetime import date, timedelta

from app.backtesting import screen
from app.backtesting.screen import run_active_backtest


def _daily(start, end, f):
    out, d = [], start
    while d <= end:
        out.append({"date": d.isoformat(), "close": float(f(d))})
        d += timedelta(days=1)
    return out


def _stub_prices(series):
    def gs(sym, start, end):
        bars = [b for b in series.get(sym, []) if start.isoformat() <= b["date"] <= end.isoformat()]
        return [b["date"] for b in bars], [float(b["close"]) for b in bars], "stub"
    return gs


def test_fundamental_gate_runs_and_respects_filing_date(monkeypatch):
    """A long_term (fundamental) model must actually execute the FCF gate through
    run_active_backtest AND never act on a filing before its filing date — the
    no-look-ahead invariant on the fundamental path (audit F1)."""
    h0, start, end = date(2018, 1, 1), date(2020, 1, 1), date(2021, 12, 31)
    filing = date(2020, 7, 1)  # the qualifying 10-K only becomes visible mid-window

    # Gently rising price so the name is investable throughout; fundamentals gate entry.
    monkeypatch.setattr(screen.price_store, "get_series", _stub_prices({
        "FUN": _daily(h0, end, lambda d: 50 + 20 * ((d - h0).days / (end - h0).days)),
        "SPY": _daily(h0, end, lambda d: 100.0),
    }))

    def fake_as_of(ticker, d):
        cutoff = d.isoformat() if hasattr(d, "isoformat") else str(d)[:10]
        if cutoff < filing.isoformat():
            return None  # not yet filed — invisible point-in-time
        return {"fcf": 1.0e9, "fcf_margin": 0.25, "shares": 1.0e8, "net_debt_to_fcf": 1.0}

    monkeypatch.setattr(screen, "as_of", fake_as_of)

    res = run_active_backtest(
        strategy={"category": "long_term", "name": "FundGate", "parameters": {"max_debt_to_fcf": 6}},
        universe=["FUN"], start_date=start, end_date=end, starting_cash=10000.0)

    def iso(d):  # trade dates are date objects in-memory, isoformatted only on persistence
        return d.isoformat() if hasattr(d, "isoformat") else str(d)[:10]

    buys = [t for t in res["trades"] if t["side"] == "buy"]
    assert buys, "the fundamental gate never fired — the long_term FCF path is not exercised"
    assert all(iso(t["date"]) > filing.isoformat() for t in buys), "bought FUN before its 10-K was filed (look-ahead)"
    checks = {c["id"]: c["status"] for c in res["integrity"]["checks"]}
    assert checks["fundamentals"] == "pass"


def test_short_direction_execution_and_pnl_sign(monkeypatch):
    """A short_selling model must create a short position and cover with correctly-signed
    P&L — the position-creation path the marking-layer tests never touch (audit F2)."""
    h0, start, end = date(2018, 1, 1), date(2020, 1, 1), date(2021, 12, 31)
    # Steady decline the whole way: px < SMA(100) and 120-day momentum < 0 → short entry;
    # continued fall grows the short's gain until the +25% take-profit covers it.
    monkeypatch.setattr(screen.price_store, "get_series", _stub_prices({
        "DWN": _daily(h0, end, lambda d: 100 - 65 * ((d - h0).days / (end - h0).days)),
        "SPY": _daily(h0, end, lambda d: 100.0),
    }))

    res = run_active_backtest(
        strategy={"category": "short_selling", "name": "ShortIt", "parameters": {"slow_days": 100}},
        universe=["DWN"], start_date=start, end_date=end, starting_cash=10000.0)

    shorts = [t for t in res["trades"] if t["side"] == "short"]
    covers = [t for t in res["trades"] if t["side"] == "cover"]
    assert shorts, "no short position was ever opened"
    assert covers, "the short never covered"
    # Covering a short at a lower price than entry must book a positive P&L.
    tp_cover = next((c for c in covers if "take-profit" in c["reason"]), covers[0])
    assert tp_cover["price"] < shorts[0]["price"]
    assert tp_cover["pnl"] > 0, "short P&L sign is wrong — profitable decline booked as a loss"
    # A profitable short must lift ending equity above the starting cash.
    assert res["equity_curve"][-1]["equity"] > 10000.0
