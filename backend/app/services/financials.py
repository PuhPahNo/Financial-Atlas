"""Financial statement & cash-flow-analysis services (PRD 12, 13).

Statements come straight from the provider chain (EDGAR). The cash-flow
analysis joins income + cash-flow data per fiscal period and computes the
derived metrics defined in the Glossary (FCF margin, conversion, per share,
capex % of revenue, capital returns, etc.). Derived values that would divide by
a non-positive denominator return ``None`` (rendered "N/M") rather than mislead.
"""
from __future__ import annotations

from ..providers.base import Period
from ..providers.registry import run_chain

_KIND = {
    "income": ("income", "get_income_statements"),
    "balance": ("balance", "get_balance_sheets"),
    "cashflow": ("cashflow", "get_cash_flows"),
}


def statements(ticker: str, kind: str, period: Period):
    domain, method = _KIND[kind]
    rows, served_by = run_chain(domain, method, ticker, period=period)
    return [r.model_dump() for r in rows], served_by


def _latest(rows: list, attr: str | None = None):
    for r in rows:
        if attr is None or getattr(r, attr) is not None:
            return r
    return None


def _safe_div(a, b):
    if a is None or b is None or b == 0:
        return None
    return a / b


def cash_flow_analysis(ticker: str, period: Period = Period.ANNUAL) -> dict:
    """Derived FCF metric series, one entry per fiscal period (PRD 13)."""
    income, _ = run_chain("income", "get_income_statements", ticker, period=period)
    cashflow, served_by = run_chain("cashflow", "get_cash_flows", ticker, period=period)
    income_by_key = {(s.fiscal_year, s.period): s for s in income}

    periods = []
    for cf in cashflow:  # already sorted newest-first
        inc = income_by_key.get((cf.fiscal_year, cf.period))
        revenue = inc.revenue if inc else None
        net_income = inc.net_income if inc else None
        shares = (inc.weighted_average_shares_diluted or inc.weighted_average_shares) if inc else None

        ocf = cf.operating_cash_flow
        capex = abs(cf.capital_expenditures) if cf.capital_expenditures is not None else None
        fcf = cf.free_cash_flow if cf.free_cash_flow is not None else (
            ocf - capex if (ocf is not None and capex is not None) else None)
        buybacks = abs(cf.share_repurchases) if cf.share_repurchases is not None else None
        dividends = abs(cf.dividends_paid) if cf.dividends_paid is not None else None
        debt_issued = cf.debt_issued
        debt_repaid = abs(cf.debt_repaid) if cf.debt_repaid is not None else None

        capital_returned = (buybacks or 0) + (dividends or 0) if (buybacks is not None or dividends is not None) else None

        periods.append({
            "fiscal_year": cf.fiscal_year,
            "period": cf.period,
            "operating_cash_flow": ocf,
            "capex": capex,
            "free_cash_flow": fcf,
            "fcf_margin": _safe_div(fcf, revenue),
            "fcf_conversion": _safe_div(fcf, net_income) if (net_income or 0) > 0 else None,
            "fcf_per_share": _safe_div(fcf, shares),
            "capex_pct_revenue": _safe_div(capex, revenue),
            "buybacks": buybacks,
            "dividends": dividends,
            "debt_issued": debt_issued,
            "debt_repaid": debt_repaid,
            "net_debt_issuance": (debt_issued or 0) - (debt_repaid or 0) if (debt_issued is not None or debt_repaid is not None) else None,
            "capital_returned": capital_returned,
            "payout_vs_fcf": _safe_div(capital_returned, fcf) if (fcf or 0) > 0 else None,
            "stock_based_compensation": cf.stock_based_compensation,
            "sbc_pct_ocf": _safe_div(cf.stock_based_compensation, ocf) if (ocf or 0) > 0 else None,
            "reinvestment_rate": _safe_div(capex, ocf) if (ocf or 0) > 0 else None,
            "revenue": revenue,
            "net_income": net_income,
        })
    return {"periods": periods, "served_by": served_by}
