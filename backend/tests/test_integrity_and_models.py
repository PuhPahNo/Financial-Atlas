"""Backtest integrity (next-bar fills, PIT extraction, quota) and the mainstream model
library (F-Score, Magic Formula, momentum, expanded metrics)."""
from datetime import date, timedelta

from app.backtesting import engine as eng
from app.backtesting import factors, metrics, screen
from app.backtesting.screen import piotroski_f_score
from app.core import quota
from app.providers.base import Period
from app.providers.sec_edgar import _build_periods


def _daily(start, end, f):
    out, d = [], start
    while d <= end:
        out.append({"date": d.isoformat(), "close": float(f(d))})
        d += timedelta(days=1)
    return out


def _stub(series):
    def gs(sym, start, end):
        bars = [b for b in series.get(sym, []) if start.isoformat() <= b["date"] <= end.isoformat()]
        return [b["date"] for b in bars], [float(b["close"]) for b in bars], "stub"
    return gs


# --------------------------------------------------------------------------- #
# Next-bar execution                                                          #
# --------------------------------------------------------------------------- #

def test_rule_engine_fills_on_bar_after_signal(monkeypatch):
    """A pct_gain signal firing on day F must fill at F+1's close, never F's own bar."""
    h0, end = date(2020, 1, 1), date(2020, 1, 20)
    jump_day = date(2020, 1, 8)

    def ref_price(d):  # +10% single-day jump on jump_day → signal fires that evening
        return 110.0 if d >= jump_day else 100.0

    series = {"INST": _daily(h0, end, lambda d: 100.0),
              "REF": _daily(h0, end, ref_price),
              "SPY": _daily(h0, end, lambda d: 100.0)}
    monkeypatch.setattr(eng.price_store, "get_series", _stub(series))

    res = eng.run_backtest(
        strategy={"category": "short_term", "name": "NB", "parameters": {
            "tickers": ["INST"],
            "rules": {"instrument": "INST", "direction": "long",
                      "signal": {"type": "pct_gain", "reference": "REF", "pct": 5, "window_days": 1},
                      "take_profit_pct": 0.99, "stop_loss_pct": 0.99},
        }},
        tickers=["INST"], start_date=h0, end_date=end, starting_cash=10000.0)
    buys = [t for t in res["trades"] if t["side"] == "buy"]
    assert buys and buys[0]["date"] == jump_day + timedelta(days=1)
    checks = {c["id"]: c["status"] for c in res["integrity"]["checks"]}
    assert checks["execution"] == "pass" and checks["adjusted_prices"] == "pass"


def test_active_screener_fills_day_after_criteria_met(monkeypatch):
    """Eligibility uses data through yesterday; the fill happens at today's close."""
    h0, start, end = date(2018, 1, 1), date(2020, 1, 1), date(2020, 12, 31)
    turn = date(2020, 6, 1)

    def price(d):  # decline, then a strong rise that creates eligibility at `turn`+
        if d <= turn:
            return 100 - 40 * ((d - h0).days / (turn - h0).days)
        return 60 + 100 * ((d - turn).days / (end - turn).days)

    monkeypatch.setattr(screen.price_store, "get_series",
                        _stub({"MOM": _daily(h0, end, price), "SPY": _daily(h0, end, lambda d: 100.0)}))
    res = screen.run_active_backtest(
        strategy={"category": "short_term", "name": "M", "parameters": {"take_profit_pct": 0.99, "stop_loss_pct": 0.99}},
        universe=["MOM"], start_date=start, end_date=end, starting_cash=10000.0)
    buys = [t for t in res["trades"] if t["side"] == "buy"]
    assert buys
    first_buy = buys[0]["date"]
    # The day before the fill, the name must already have been eligible on its own data —
    # i.e. the engine did not use the fill day's price to decide.
    dates = [b["date"] for b in _daily(h0, end, price)]
    closes = [b["close"] for b in _daily(h0, end, price)]
    ok_prev, _, _ = screen.eligible("short_term", {}, "MOM", first_buy - timedelta(days=1), dates, closes)
    assert ok_prev


# --------------------------------------------------------------------------- #
# Point-in-time EDGAR extraction (originally-filed values)                    #
# --------------------------------------------------------------------------- #

def test_build_periods_point_in_time_prefers_original_filing():
    entries = [
        {"start": "2020-01-01", "end": "2020-12-31", "val": 100.0, "form": "10-K",
         "filed": "2021-02-01", "fp": "FY"},                                    # original 10-K
        {"start": "2020-01-01", "end": "2020-12-31", "val": 110.0, "form": "10-K",
         "filed": "2022-02-01", "fp": "FY"},                                    # restated comparative
    ]
    facts = {"us-gaap": {"NetIncomeLoss": {"units": {"USD": entries}}}}
    tag_map = {"net_income": ["NetIncomeLoss"]}

    pit = _build_periods(facts, tag_map, Period.ANNUAL, instant=False, point_in_time=True)
    assert pit[(2020, "FY")]["net_income"] == 100.0
    assert pit[(2020, "FY")]["filing_date"] == "2021-02-01"

    restated = _build_periods(facts, tag_map, Period.ANNUAL, instant=False)
    assert restated[(2020, "FY")]["net_income"] == 110.0


# --------------------------------------------------------------------------- #
# Piotroski F-Score                                                           #
# --------------------------------------------------------------------------- #

def _pit_row(**kw):
    base = dict(net_income=100.0, total_assets=1000.0, operating_cash_flow=150.0,
                long_term_debt=200.0, total_current_assets=400.0, total_current_liabilities=200.0,
                shares=100.0, gross_profit=300.0, revenue=900.0)
    base.update(kw)
    return base


def test_f_score_perfect_year_scores_nine():
    prev = _pit_row(net_income=50.0, operating_cash_flow=60.0, long_term_debt=300.0,
                    total_current_assets=300.0, total_current_liabilities=200.0,
                    shares=110.0, gross_profit=200.0, revenue=800.0, total_assets=1000.0)
    assert piotroski_f_score(_pit_row(), prev) == 9


def test_f_score_penalizes_dilution_and_leverage():
    prev = _pit_row(net_income=50.0, operating_cash_flow=60.0, long_term_debt=100.0,  # leverage UP now
                    total_current_assets=300.0, total_current_liabilities=200.0,
                    shares=90.0, gross_profit=200.0, revenue=800.0)                    # shares UP now
    assert piotroski_f_score(_pit_row(), prev) == 7


def test_f_score_requires_prior_year():
    assert piotroski_f_score(_pit_row(), None) is None


# --------------------------------------------------------------------------- #
# Mainstream factor helpers                                                   #
# --------------------------------------------------------------------------- #

def test_momentum_12_1_skips_latest_month():
    # 12 months of strong gains, then a brutal final month: plain 12m momentum is dragged
    # down by the reversal month; 12-1 ignores it.
    closes = [100 * (1.01 ** i) for i in range(252)] + [50.0] * 21
    k = len(closes)
    plain = factors.momentum_at(closes, k, 252)
    skipped = factors.momentum_12_1_at(closes, k)
    assert skipped is not None and plain is not None and skipped > plain


def test_rsi_extremes():
    up = [float(i) for i in range(1, 30)]
    down = [float(30 - i) for i in range(1, 30)]
    assert factors.rsi_at(up, len(up), 14) == 100.0
    assert factors.rsi_at(down, len(down), 14) == 0.0


def test_high_proximity():
    closes = [100.0] * 251 + [90.0]
    assert abs(factors.high_proximity_at(closes, len(closes), 252) - 0.9) < 1e-9


# --------------------------------------------------------------------------- #
# Expanded metrics                                                            #
# --------------------------------------------------------------------------- #

def test_summarize_includes_risk_panel():
    points, equity, bench = [], 10000.0, 10000.0
    d = date(2020, 1, 1)
    for i in range(252):
        equity *= 1.001 if i % 2 == 0 else 0.9995
        bench *= 1.0008 if i % 2 == 0 else 0.9999  # varying benchmark so beta is defined
        points.append({"date": d, "equity": equity, "benchmark_equity": bench})
        d += timedelta(days=1)
    m = metrics.summarize(points, [], 10000.0)
    for key in ("volatility", "sharpe", "sortino", "calmar", "benchmark_return", "alpha", "beta"):
        assert m[key] is not None, key
    assert m["sharpe"] > 0 and m["volatility"] > 0


# --------------------------------------------------------------------------- #
# FMP daily quota guard                                                        #
# --------------------------------------------------------------------------- #

def test_quota_budget_blocks_after_limit(monkeypatch):
    store: dict = {}
    monkeypatch.setattr(quota.cache, "peek", lambda ns, k, ttl: store.get((ns, k)))
    monkeypatch.setattr(quota.cache, "put", lambda ns, k, v: store.__setitem__((ns, k), v))
    assert quota.available("fmp", 2)
    quota.spend("fmp")
    assert quota.available("fmp", 2)
    quota.spend("fmp")
    assert not quota.available("fmp", 2)
    assert quota.available("fmp", 0)  # 0 disables the guard
