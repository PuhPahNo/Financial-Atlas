"""Company overview service (PRD 10) — profile + computed key metrics.

Combines EDGAR profile, a Yahoo quote, and the latest annual fundamentals into
the headline metric grid. Metrics are computed per the Glossary; any metric
whose inputs are missing/invalid is returned as ``None`` (rendered "N/M"),
never a misleading zero.
"""
from __future__ import annotations

from ..providers.base import Period
from ..providers.registry import run_chain
from . import prices


def _latest_with(rows, attr):
    for r in rows:
        if getattr(r, attr) is not None:
            return r
    return rows[0] if rows else None


def _net_debt(bal) -> float | None:
    if bal is None or bal.total_debt is None:
        return None
    cash = (bal.cash_and_equivalents or 0) + (bal.short_term_investments or 0)
    return bal.total_debt - cash


def _ebitda(inc, cf) -> float | None:
    if inc is None or inc.operating_income is None:
        return None
    da = cf.depreciation_and_amortization if cf else None
    return inc.operating_income + (da or 0)


def overview(ticker: str) -> dict:
    profile, profile_src = run_chain("profile", "get_company_profile", ticker)
    try:
        q, _ = prices.quote(ticker)
    except Exception:
        q = None

    income, _ = run_chain("income", "get_income_statements", ticker, period=Period.ANNUAL)
    balance, _ = run_chain("balance", "get_balance_sheets", ticker, period=Period.ANNUAL)
    cashflow, _ = run_chain("cashflow", "get_cash_flows", ticker, period=Period.ANNUAL)

    inc = _latest_with(income, "net_income")
    bal = _latest_with(balance, "total_assets")
    cf = _latest_with(cashflow, "operating_cash_flow")

    price = q.price if q else None
    shares = profile.shares_outstanding or (inc.weighted_average_shares_diluted if inc else None)
    # Prefer the data provider's reported market cap (correct for dual-class/ADRs);
    # fall back to price × shares.
    market_cap = (q.market_cap if (q and q.market_cap) else (price * shares if (price and shares) else None))
    net_debt = _net_debt(bal)
    ebitda = _ebitda(inc, cf)
    fcf = cf.free_cash_flow if cf else None
    eps = inc.eps_diluted if inc else None
    dps = (abs(cf.dividends_paid) / shares) if (cf and cf.dividends_paid and shares) else None

    key_metrics = {
        "market_cap": market_cap,
        "price": price,
        "change_abs": q.change_abs if q else None,
        "change_pct": q.change_pct if q else None,
        "week52_high": q.week52_high if q else None,
        "week52_low": q.week52_low if q else None,
        "pe": (price / eps) if (price and eps and eps > 0) else None,
        "price_to_fcf": (market_cap / fcf) if (market_cap and fcf and fcf > 0) else None,
        "ev_ebitda": ((market_cap + (net_debt or 0)) / ebitda) if (market_cap and ebitda and ebitda > 0) else None,
        "dividend_yield": (dps / price) if (dps and price) else None,
        "shares_outstanding": shares,
        "net_debt": net_debt,
        "volume": q.volume if q else None,
    }
    return {
        "profile": profile.model_dump(),
        "key_metrics": key_metrics,
        "served_by": profile_src,
    }
