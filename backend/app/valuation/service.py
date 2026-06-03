"""Valuation orchestration (PRD 14 §6-7).

Assembles model inputs from the latest annual fundamentals + current price,
applies default assumptions (with history-derived growth) and bull/base/bear
scenario overrides, runs every model via the pure engine, and blends. Custom
assumptions from the POST endpoint override the defaults.
"""
from __future__ import annotations

from ..providers.base import Period
from ..providers.registry import run_chain
from ..services import prices
from . import engine


def _latest(rows, attr):
    for r in rows:
        if getattr(r, attr) is not None:
            return r
    return rows[0] if rows else None


def _revenue_cagr(income) -> float:
    rev = [(s.fiscal_year, s.revenue) for s in income if s.revenue and s.revenue > 0]
    rev.sort()
    if len(rev) < 2:
        return 0.05
    first, last = rev[0][1], rev[-1][1]
    years = rev[-1][0] - rev[0][0]
    if years <= 0 or first <= 0:
        return 0.05
    cagr = (last / first) ** (1 / years) - 1
    return max(0.0, min(cagr, 0.20))  # clamp to sane range


def _inputs(ticker: str) -> dict:
    income, _ = run_chain("income", "get_income_statements", ticker, period=Period.ANNUAL)
    balance, _ = run_chain("balance", "get_balance_sheets", ticker, period=Period.ANNUAL)
    cashflow, _ = run_chain("cashflow", "get_cash_flows", ticker, period=Period.ANNUAL)
    inc, bal, cf = _latest(income, "net_income"), _latest(balance, "total_assets"), _latest(cashflow, "operating_cash_flow")

    shares = (inc.weighted_average_shares_diluted or inc.weighted_average_shares) if inc else None
    cash = ((bal.cash_and_equivalents or 0) + (bal.short_term_investments or 0)) if bal else 0
    net_debt = (bal.total_debt - cash) if (bal and bal.total_debt is not None) else 0.0
    da = cf.depreciation_and_amortization if cf else None
    ebitda = (inc.operating_income + (da or 0)) if (inc and inc.operating_income is not None) else None
    dps = (abs(cf.dividends_paid) / shares) if (cf and cf.dividends_paid and shares) else 0.0
    return {
        "fcf0": cf.free_cash_flow if cf else None,
        "net_income": inc.net_income if inc else None,
        "da": da or 0.0,
        "maintenance_capex": da if da else (abs(cf.capital_expenditures) if (cf and cf.capital_expenditures) else 0.0),
        "eps": inc.eps_diluted if inc else None,
        "revenue": inc.revenue if inc else None,
        "ebitda": ebitda,
        "net_debt": net_debt,
        "shares": shares or 0.0,
        "dividend_per_share": dps,
        "hist_growth": _revenue_cagr(income),
    }


def _defaults(inp: dict) -> dict:
    g = inp["hist_growth"]
    return {
        "growth_1_5": g, "growth_6_10": g / 2,
        "discount_rate": 0.10, "terminal_growth": 0.025,
        "eps_growth": g, "years": 5,
        "fair_pe": 18.0, "fair_ev_ebitda": 12.0, "fair_ev_sales": 3.0,
        "required_return": 0.09, "dividend_growth": min(g, 0.06),
    }


# Scenarios adjust the user's base assumptions RELATIVELY so a custom discount
# rate / terminal growth flows through (base scenario = no change).
_SCENARIOS = {
    "bear": {"growth_mult": 0.5, "discount_delta": 0.02, "terminal_delta": -0.005, "multiple_mult": 0.8},
    "base": {"growth_mult": 1.0, "discount_delta": 0.0, "terminal_delta": 0.0, "multiple_mult": 1.0},
    "bull": {"growth_mult": 1.5, "discount_delta": -0.01, "terminal_delta": 0.005, "multiple_mult": 1.2},
}


def _run_models(inp: dict, a: dict) -> list[dict]:
    return [
        engine.discounted_cash_flow(fcf0=inp["fcf0"], growth_1_5=a["growth_1_5"], growth_6_10=a["growth_6_10"],
                                    discount_rate=a["discount_rate"], terminal_growth=a["terminal_growth"],
                                    net_debt=inp["net_debt"], shares=inp["shares"]),
        engine.owner_earnings(net_income=inp["net_income"] or 0, depreciation_amortization=inp["da"],
                              maintenance_capex=inp["maintenance_capex"], working_capital_change=0.0,
                              growth=a["growth_1_5"], discount_rate=a["discount_rate"],
                              terminal_growth=a["terminal_growth"], net_debt=inp["net_debt"], shares=inp["shares"]),
        engine.earnings_multiple(eps=inp["eps"], growth=a["eps_growth"], years=a["years"],
                                 fair_pe=a["fair_pe"], discount_rate=a["discount_rate"]),
        engine.revenue_multiple(revenue=inp["revenue"], growth=a["growth_1_5"], years=a["years"],
                                fair_ev_sales=a["fair_ev_sales"], net_debt=inp["net_debt"],
                                shares=inp["shares"], discount_rate=a["discount_rate"]),
        engine.ebitda_multiple(ebitda=inp["ebitda"], growth=a["growth_1_5"], years=a["years"],
                               fair_ev_ebitda=a["fair_ev_ebitda"], net_debt=inp["net_debt"],
                               shares=inp["shares"], discount_rate=a["discount_rate"]),
        engine.dividend_discount(dividend_per_share=inp["dividend_per_share"], growth=a["dividend_growth"],
                                 required_return=a["required_return"]),
    ]


def _apply_scenario(base: dict, s: dict) -> dict:
    a = dict(base)
    a["growth_1_5"] = base["growth_1_5"] * s["growth_mult"]
    a["growth_6_10"] = base["growth_6_10"] * s["growth_mult"]
    a["eps_growth"] = base["eps_growth"] * s["growth_mult"]
    a["dividend_growth"] = base["dividend_growth"] * s["growth_mult"]
    a["discount_rate"] = base["discount_rate"] + s["discount_delta"]
    a["terminal_growth"] = max(0.0, min(base["terminal_growth"] + s["terminal_delta"], a["discount_rate"] - 0.005))
    a["fair_pe"] = base["fair_pe"] * s["multiple_mult"]
    a["fair_ev_ebitda"] = base["fair_ev_ebitda"] * s["multiple_mult"]
    a["fair_ev_sales"] = base["fair_ev_sales"] * s["multiple_mult"]
    return a


def valuate(ticker: str, *, assumptions: dict | None = None, weights: dict | None = None) -> dict:
    # Foreign private issuers (ADRs, e.g. BABA/BIDU) file 20-F with ordinary-share
    # counts & per-ordinary-share figures, while the price is per ADS (often an 8:1
    # ratio). Mixing them yields nonsense per-share fair values, so we don't fake one.
    try:
        profile, _ = run_chain("profile", "get_company_profile", ticker)
    except Exception:
        profile = None
    if profile is not None and getattr(profile, "foreign_filer", False):
        try:
            current_price = prices.quote(ticker)[0].price
        except Exception:
            current_price = None
        return {
            "ticker": ticker.upper(), "current_price": current_price,
            "models": [], "blended_fair_value": None, "applied_weights": {},
            "scenarios": {"bear": None, "base": None, "bull": None},
            "margin_of_safety": None, "assumptions": {}, "inputs": {},
            "note": "Valuation isn't supported for foreign private issuers (ADRs): EDGAR reports ordinary-share counts and per-ordinary-share figures, which aren't directly comparable to the per-ADS trading price. Financial statements are still available.",
        }

    inp = _inputs(ticker)
    base_assumptions = _defaults(inp)
    if assumptions:
        base_assumptions.update({k: v for k, v in assumptions.items() if v is not None})
    w = weights or engine.DEFAULT_WEIGHTS

    try:
        q, _ = prices.quote(ticker)
        current_price = q.price
    except Exception:
        current_price = None

    scenario_blends = {}
    base_models = None
    for name, s in _SCENARIOS.items():
        a = _apply_scenario(base_assumptions, s)
        models = _run_models(inp, a)
        blend = engine.blended(models, w)
        scenario_blends[name] = blend["blended_fair_value"]
        if name == "base":
            base_models = models
            base_blend = blend

    return {
        "ticker": ticker.upper(),
        "current_price": current_price,
        "models": base_models,
        "blended_fair_value": base_blend["blended_fair_value"],
        "applied_weights": base_blend["applied_weights"],
        "scenarios": scenario_blends,
        "margin_of_safety": engine.margin_of_safety(base_blend["blended_fair_value"], current_price),
        "assumptions": base_assumptions,
        "inputs": inp,
    }
