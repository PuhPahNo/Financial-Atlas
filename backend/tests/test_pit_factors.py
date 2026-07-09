"""Point-in-time factor + fundamentals helpers (PRD backtest-integrity)."""
from datetime import date

from app.backtesting import factors
from app.backtesting import pit_fundamentals as pit
from app.providers.base import CashFlowStatement


def test_factors_ignore_data_after_D():
    dates = ["2020-01-01", "2020-01-02", "2020-01-03", "2020-01-04"]
    closes = [10, 11, 12, 100]
    D = date(2020, 1, 3)  # the 100 spike on the 4th must be invisible at D
    k = factors.idx_asof(dates, D)
    assert k == 3
    assert factors.close_at(dates, closes, D) == 12
    assert factors.sma_at(closes, k, 3) == (10 + 11 + 12) / 3
    assert factors.momentum_at(closes, k, 2) == 12 / 10 - 1
    assert factors.high_proximity_at(closes, k, 3) == 1.0


def test_as_of_respects_filing_dates(monkeypatch):
    cf_old = CashFlowStatement(fiscal_year=2019, period="FY", filing_date="2020-02-15",
                               operating_cash_flow=100.0, capital_expenditures=20.0, free_cash_flow=80.0)
    cf_new = CashFlowStatement(fiscal_year=2020, period="FY", filing_date="2021-02-15",
                               operating_cash_flow=200.0, capital_expenditures=40.0, free_cash_flow=160.0)
    monkeypatch.setattr(pit.sec_edgar, "get_cash_flows", lambda t, **k: [cf_new, cf_old])
    monkeypatch.setattr(pit.sec_edgar, "get_income_statements", lambda t, **k: [])
    monkeypatch.setattr(pit.sec_edgar, "get_balance_sheets", lambda t, **k: [])
    pit._ROWS_MEM.clear()
    pit._ATTEMPTED.discard("X")

    # Mid-2020: only the FY2019 10-K (filed 2020-02-15) was known.
    f = pit.as_of("X", date(2020, 6, 1))
    assert f["fiscal_year"] == 2019 and f["fcf"] == 80.0
    # Mid-2021: the FY2020 10-K is now known.
    f2 = pit.as_of("X", date(2021, 6, 1))
    assert f2["fiscal_year"] == 2020 and f2["fcf"] == 160.0
    # Before any filing was available -> None (no look-ahead).
    assert pit.as_of("X", date(2019, 1, 1)) is None
