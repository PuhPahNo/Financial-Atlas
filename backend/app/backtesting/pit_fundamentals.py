"""Point-in-time fundamentals, backed by a compact precomputed table (PRD oom-fix).

``as_of(ticker, D)`` returns the most recent annual fundamentals filed on or before D. It
reads tiny rows from the ``pit_fundamentals`` DB table; on a miss it extracts every annual
filing once from EDGAR companyfacts, stores the compact rows, and serves from them forever
after. This keeps a full-S&P-500 fundamental scan fast and low-memory — backtests never
re-parse ~3.7MB of XBRL per ticker, and nothing big is held in RAM.
"""
from __future__ import annotations

from datetime import date

from ..db import PitFundamental, session_scope
from ..providers.registry import sec_edgar

# Process-level memo so a backtest that calls as_of(ticker, ·) thousands of times across
# rebalance days hits the DB at most once per ticker. Rows are tiny; bounded loosely.
_ROWS_MEM: dict[str, list[dict]] = {}
_ATTEMPTED: set[str] = set()  # tickers whose EDGAR extraction we've already tried this run

_FIELDS = ("filing_date", "fcf", "revenue", "operating_cash_flow", "fcf_margin",
           "fcf_conversion", "net_debt", "net_debt_to_fcf", "dividends_paid", "shares")


def _iso(d) -> str:
    return d.isoformat() if isinstance(d, date) else str(d)[:10]


def _annual_rows(ticker: str) -> list[dict] | None:
    """Extract one compact row per annual filing from EDGAR. None if no coverage."""
    try:
        income = sec_edgar.get_income_statements(ticker)
        balance = sec_edgar.get_balance_sheets(ticker)
        cashflow = sec_edgar.get_cash_flows(ticker)
    except Exception:  # noqa: BLE001 — no EDGAR coverage (e.g. ETFs) / fetch error
        return None
    inc_by = {s.fiscal_year: s for s in income}
    bal_by = {s.fiscal_year: s for s in balance}
    rows: list[dict] = []
    for cf in cashflow:
        if not getattr(cf, "filing_date", None):
            continue
        fcf = cf.free_cash_flow
        if fcf is None and cf.operating_cash_flow is not None and cf.capital_expenditures is not None:
            fcf = cf.operating_cash_flow - abs(cf.capital_expenditures)
        if fcf is None:
            continue
        inc, bal = inc_by.get(cf.fiscal_year), bal_by.get(cf.fiscal_year)
        revenue = inc.revenue if inc else None
        shares = (inc.weighted_average_shares or inc.weighted_average_shares_diluted) if inc else None
        net_debt = None
        if bal is not None:
            net_debt = (bal.total_debt or 0.0) - ((bal.cash_and_equivalents or 0.0) + (bal.short_term_investments or 0.0))
        rows.append({
            "ticker": ticker.upper(), "fiscal_year": cf.fiscal_year, "filing_date": cf.filing_date,
            "fcf": fcf, "revenue": revenue, "operating_cash_flow": cf.operating_cash_flow,
            "fcf_margin": (fcf / revenue) if (fcf is not None and revenue) else None,
            "fcf_conversion": (fcf / cf.operating_cash_flow) if (fcf is not None and cf.operating_cash_flow) else None,
            "net_debt": net_debt,
            "net_debt_to_fcf": (net_debt / fcf) if (net_debt is not None and fcf and fcf > 0) else None,
            "dividends_paid": abs(cf.dividends_paid) if cf.dividends_paid is not None else 0.0,
            "shares": shares,
        })
    return rows


def _row_to_dict(r: PitFundamental) -> dict:
    d = {"ticker": r.ticker, "fiscal_year": r.fiscal_year}
    for f in _FIELDS:
        d[f] = getattr(r, f)
    return d


def _rows_from_db(ticker: str) -> list[dict]:
    with session_scope() as s:
        return [_row_to_dict(r) for r in s.query(PitFundamental).filter(PitFundamental.ticker == ticker.upper()).all()]


def _store(ticker: str, rows: list[dict]) -> None:
    if not rows:
        return
    with session_scope() as s:
        for r in rows:
            existing = s.query(PitFundamental).filter_by(ticker=r["ticker"], fiscal_year=r["fiscal_year"]).first()
            if existing:
                for f in _FIELDS:
                    setattr(existing, f, r[f])
            else:
                s.add(PitFundamental(**r))


def as_of(ticker: str, D) -> dict | None:
    """Most recent annual fundamentals known as of D, or None. Reads the compact table;
    extracts + persists from EDGAR once on a miss. Never raises."""
    tk = ticker.upper()
    rows = _ROWS_MEM.get(tk)
    if rows is None:
        try:
            rows = _rows_from_db(tk)
        except Exception:  # noqa: BLE001
            rows = []
        if not rows and tk not in _ATTEMPTED:
            _ATTEMPTED.add(tk)
            extracted = _annual_rows(tk)
            if extracted:
                try:
                    _store(tk, extracted)
                except Exception:  # noqa: BLE001 — serving the data matters more than persisting it
                    pass
                rows = extracted
            else:
                rows = []
        if len(_ROWS_MEM) > 2000:
            _ROWS_MEM.clear()
        _ROWS_MEM[tk] = rows
    if not rows:
        return None
    cutoff = _iso(D)
    eligible = [r for r in rows if r.get("filing_date") and r["filing_date"] <= cutoff]
    if not eligible:
        return None
    return max(eligible, key=lambda r: (r["fiscal_year"], r.get("filing_date") or ""))


def precompute_universe(tickers: list[str]) -> dict:
    """Bulk-populate the table (e.g. from a warm job). as_of() does the extract+store."""
    with_data = 0
    for t in tickers:
        try:
            if as_of(t, date.today()) is not None:
                with_data += 1
        except Exception:  # noqa: BLE001
            continue
    return {"tickers": len(tickers), "with_data": with_data}
