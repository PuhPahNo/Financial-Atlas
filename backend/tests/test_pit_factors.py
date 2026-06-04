"""Point-in-time factor + fundamentals helpers (PRD backtest-integrity)."""
from datetime import date

from app.backtesting import factors
from app.backtesting import pit_fundamentals as pit
from app.providers.base import CashFlowStatement


def _bars(series):
    return [{"date": d, "close": c} for d, c in series]


def test_factors_ignore_data_after_D():
    bars = _bars([("2020-01-01", 10), ("2020-01-02", 11), ("2020-01-03", 12), ("2020-01-04", 100)])
    D = date(2020, 1, 3)  # the 100 spike on the 4th must be invisible at D
    assert factors.close_on(bars, D) == 12
    assert factors.sma(bars, D, 3) == (10 + 11 + 12) / 3
    assert factors.momentum(bars, D, 2) == 12 / 10 - 1
    assert factors.new_high(bars, D, 2) is True


def test_as_of_respects_filing_dates(monkeypatch):
    cf_old = CashFlowStatement(fiscal_year=2019, period="FY", filing_date="2020-02-15",
                               operating_cash_flow=100.0, capital_expenditures=20.0, free_cash_flow=80.0)
    cf_new = CashFlowStatement(fiscal_year=2020, period="FY", filing_date="2021-02-15",
                               operating_cash_flow=200.0, capital_expenditures=40.0, free_cash_flow=160.0)
    monkeypatch.setattr(pit.sec_edgar, "get_cash_flows", lambda t, **k: [cf_new, cf_old])
    monkeypatch.setattr(pit.sec_edgar, "get_income_statements", lambda t, **k: [])
    monkeypatch.setattr(pit.sec_edgar, "get_balance_sheets", lambda t, **k: [])

    # Mid-2020: only the FY2019 10-K (filed 2020-02-15) was known.
    f = pit.as_of("X", date(2020, 6, 1))
    assert f["fiscal_year"] == 2019 and f["fcf"] == 80.0
    # Mid-2021: the FY2020 10-K is now known.
    f2 = pit.as_of("X", date(2021, 6, 1))
    assert f2["fiscal_year"] == 2020 and f2["fcf"] == 160.0
    # Before any filing was available -> None (no look-ahead).
    assert pit.as_of("X", date(2019, 1, 1)) is None
