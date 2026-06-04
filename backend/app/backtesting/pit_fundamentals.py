"""Point-in-time fundamentals from EDGAR companyfacts (PRD backtest-integrity).

Each XBRL value carries a ``filed`` date (surfaced as ``filing_date`` on the provider's
statement objects), so we can reconstruct what was *known* as of any historical date D:
take the most recent annual statement whose filing date is on or before D. One cached
``companyfacts`` fetch per ticker; all as-of filtering is pure in-memory work — free, and
no per-rebalance network calls, so latency/UX stay intact.
"""
from __future__ import annotations

from datetime import date

from ..providers.registry import sec_edgar


def _iso(d) -> str:
    return d.isoformat() if isinstance(d, date) else str(d)[:10]


# Parsed statement lists are immutable for the run (companyfacts is cached 7 days), so
# memoize per ticker — otherwise each rebalance re-parses the full companyfacts, which is
# the one thing that would hurt backtest latency. Bounded to keep memory in check.
_STMT_MEM: dict[str, tuple] = {}


def _statements(ticker: str):
    key = ticker.upper()
    cached = _STMT_MEM.get(key)
    if cached is not None:
        return cached
    try:
        stmts = (
            sec_edgar.get_income_statements(ticker),
            sec_edgar.get_balance_sheets(ticker),
            sec_edgar.get_cash_flows(ticker),
        )
    except Exception:  # noqa: BLE001 — no coverage / fetch error → simply not eligible
        return None
    if len(_STMT_MEM) > 60:
        _STMT_MEM.clear()
    _STMT_MEM[key] = stmts
    return stmts


def _latest_filed_by(statements: list, cutoff: str):
    """Most recent statement (by fiscal year/period) whose filing_date <= cutoff."""
    filed = [s for s in statements if getattr(s, "filing_date", None) and s.filing_date <= cutoff]
    if not filed:
        return None
    return max(filed, key=lambda s: (s.fiscal_year, s.period, s.filing_date or ""))


def as_of(ticker: str, D) -> dict | None:
    """Derived annual fundamentals known as of date D, or None if nothing was filed by D
    (or the ticker has no EDGAR coverage). Never raises."""
    cutoff = _iso(D)
    stmts = _statements(ticker)
    if stmts is None:
        return None
    income, balance, cashflow = stmts

    cf = _latest_filed_by(cashflow, cutoff)
    if cf is None:  # free cash flow is the backbone of every fundamental gate
        return None
    inc = _latest_filed_by(income, cutoff)
    bal = _latest_filed_by(balance, cutoff)

    fcf = cf.free_cash_flow
    if fcf is None and cf.operating_cash_flow is not None and cf.capital_expenditures is not None:
        fcf = cf.operating_cash_flow - abs(cf.capital_expenditures)

    revenue = inc.revenue if inc else None
    shares = (inc.weighted_average_shares or inc.weighted_average_shares_diluted) if inc else None

    net_debt = None
    if bal is not None:
        total_debt = bal.total_debt or 0.0
        cash = (bal.cash_and_equivalents or 0.0) + (bal.short_term_investments or 0.0)
        net_debt = total_debt - cash

    dividends = abs(cf.dividends_paid) if cf.dividends_paid is not None else 0.0
    buybacks = abs(cf.share_repurchases) if cf.share_repurchases is not None else 0.0

    return {
        "as_of_filing": cf.filing_date,
        "fiscal_year": cf.fiscal_year,
        "fcf": fcf,
        "revenue": revenue,
        "operating_cash_flow": cf.operating_cash_flow,
        "fcf_margin": (fcf / revenue) if (fcf is not None and revenue) else None,
        "fcf_conversion": (fcf / cf.operating_cash_flow) if (fcf is not None and cf.operating_cash_flow) else None,
        "net_debt": net_debt,
        "net_debt_to_fcf": (net_debt / fcf) if (net_debt is not None and fcf and fcf > 0) else None,
        "dividends_paid": dividends,
        "share_repurchases": buybacks,
        "shares": shares,
    }
