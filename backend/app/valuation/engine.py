"""Valuation engine — pure functions (PRD 14).

Every function takes explicit inputs and returns a structured dict with the
fair value per share, the assumptions used, and intermediate values (for
transparency and reproducibility). No I/O, fully deterministic, deeply tested.

Design by Contract: discount_rate must exceed terminal/dividend growth; shares
must be positive; models that cannot apply return ``applicable=False`` with a
reason rather than a misleading number.
"""
from __future__ import annotations

from ..core.errors import ValidationError


def _na(model: str, reason: str, **assumptions) -> dict:
    return {"model": model, "applicable": False, "reason": reason,
            "fair_value_per_share": None, "assumptions": assumptions, "intermediates": {}}


def discounted_cash_flow(*, fcf0: float, growth_1_5: float, growth_6_10: float,
                         discount_rate: float, terminal_growth: float,
                         net_debt: float, shares: float) -> dict:
    """10-year two-stage DCF (PRD 14 §4.1)."""
    assumptions = dict(fcf0=fcf0, growth_1_5=growth_1_5, growth_6_10=growth_6_10,
                       discount_rate=discount_rate, terminal_growth=terminal_growth,
                       net_debt=net_debt, shares=shares)
    if shares <= 0:
        return _na("dcf", "shares must be positive", **assumptions)
    if discount_rate <= terminal_growth:
        raise ValidationError("discount_rate must exceed terminal_growth", code="INVALID_REQUEST")
    if fcf0 is None or fcf0 <= 0:
        return _na("dcf", "current FCF is not positive", **assumptions)

    pv_sum = 0.0
    fcf = fcf0
    projected = []
    for year in range(1, 11):
        g = growth_1_5 if year <= 5 else growth_6_10
        fcf = fcf * (1 + g)
        pv = fcf / (1 + discount_rate) ** year
        pv_sum += pv
        projected.append({"year": year, "fcf": fcf, "pv": pv})

    terminal_value = fcf * (1 + terminal_growth) / (discount_rate - terminal_growth)
    pv_terminal = terminal_value / (1 + discount_rate) ** 10
    enterprise_value = pv_sum + pv_terminal
    equity_value = enterprise_value - net_debt
    fair = equity_value / shares
    return {"model": "dcf", "applicable": True, "fair_value_per_share": fair, "assumptions": assumptions,
            "intermediates": {"pv_explicit": pv_sum, "terminal_value": terminal_value,
                              "pv_terminal": pv_terminal, "enterprise_value": enterprise_value,
                              "equity_value": equity_value, "projected": projected}}


def owner_earnings(*, net_income: float, depreciation_amortization: float, maintenance_capex: float,
                   working_capital_change: float, growth: float, discount_rate: float,
                   terminal_growth: float, net_debt: float, shares: float) -> dict:
    """Buffett owner-earnings, then discounted like a DCF (PRD 14 §4.2)."""
    oe0 = net_income + depreciation_amortization - abs(maintenance_capex) - working_capital_change
    base = discounted_cash_flow(fcf0=oe0, growth_1_5=growth, growth_6_10=growth,
                                discount_rate=discount_rate, terminal_growth=terminal_growth,
                                net_debt=net_debt, shares=shares)
    base["model"] = "owner_earnings"
    base["assumptions"]["owner_earnings_0"] = oe0
    return base


def earnings_multiple(*, eps: float, growth: float, years: int, fair_pe: float, discount_rate: float) -> dict:
    a = dict(eps=eps, growth=growth, years=years, fair_pe=fair_pe, discount_rate=discount_rate)
    if eps is None or eps <= 0:
        return _na("earnings_multiple", "EPS is not positive", **a)
    future_eps = eps * (1 + growth) ** years
    future_price = future_eps * fair_pe
    fair = future_price / (1 + discount_rate) ** years
    return {"model": "earnings_multiple", "applicable": True, "fair_value_per_share": fair,
            "assumptions": a, "intermediates": {"future_eps": future_eps, "future_price": future_price}}


def revenue_multiple(*, revenue: float, growth: float, years: int, fair_ev_sales: float,
                     net_debt: float, shares: float, discount_rate: float) -> dict:
    a = dict(revenue=revenue, growth=growth, years=years, fair_ev_sales=fair_ev_sales,
             net_debt=net_debt, shares=shares, discount_rate=discount_rate)
    if shares <= 0 or revenue is None or revenue <= 0:
        return _na("revenue_multiple", "revenue/shares invalid", **a)
    future_rev = revenue * (1 + growth) ** years
    future_ev = future_rev * fair_ev_sales
    future_equity = future_ev - net_debt
    future_price = future_equity / shares
    fair = future_price / (1 + discount_rate) ** years
    return {"model": "revenue_multiple", "applicable": True, "fair_value_per_share": fair,
            "assumptions": a, "intermediates": {"future_revenue": future_rev, "future_ev": future_ev}}


def ebitda_multiple(*, ebitda: float, growth: float, years: int, fair_ev_ebitda: float,
                    net_debt: float, shares: float, discount_rate: float) -> dict:
    a = dict(ebitda=ebitda, growth=growth, years=years, fair_ev_ebitda=fair_ev_ebitda,
             net_debt=net_debt, shares=shares, discount_rate=discount_rate)
    if shares <= 0 or ebitda is None or ebitda <= 0:
        return _na("ebitda_multiple", "EBITDA/shares invalid", **a)
    future_ebitda = ebitda * (1 + growth) ** years
    future_ev = future_ebitda * fair_ev_ebitda
    future_equity = future_ev - net_debt
    future_price = future_equity / shares
    fair = future_price / (1 + discount_rate) ** years
    return {"model": "ebitda_multiple", "applicable": True, "fair_value_per_share": fair,
            "assumptions": a, "intermediates": {"future_ebitda": future_ebitda, "future_ev": future_ev}}


def dividend_discount(*, dividend_per_share: float, growth: float, required_return: float) -> dict:
    a = dict(dividend_per_share=dividend_per_share, growth=growth, required_return=required_return)
    if not dividend_per_share or dividend_per_share <= 0:
        return _na("dividend_discount", "no dividend", **a)
    if required_return <= growth:
        return _na("dividend_discount", "required_return must exceed growth", **a)
    next_div = dividend_per_share * (1 + growth)
    fair = next_div / (required_return - growth)
    return {"model": "dividend_discount", "applicable": True, "fair_value_per_share": fair,
            "assumptions": a, "intermediates": {"next_dividend": next_div}}


def blended(model_results: list[dict], weights: dict[str, float]) -> dict:
    """Weighted blend over applicable models; weights renormalize to those present (PRD 14 §6)."""
    usable = {r["model"]: r["fair_value_per_share"] for r in model_results
              if r.get("applicable") and r.get("fair_value_per_share") is not None and r["fair_value_per_share"] > 0}
    active = {m: weights.get(m, 0.0) for m in usable if weights.get(m, 0.0) > 0}
    total_w = sum(active.values())
    if total_w == 0:
        return {"blended_fair_value": None, "applied_weights": {}, "components": usable}
    norm = {m: w / total_w for m, w in active.items()}
    value = sum(usable[m] * w for m, w in norm.items())
    # invariant: blend lies within [min, max] of components used
    lo, hi = min(usable[m] for m in norm), max(usable[m] for m in norm)
    assert lo - 1e-6 <= value <= hi + 1e-6, "blended value outside component bounds"
    return {"blended_fair_value": value, "applied_weights": norm, "components": usable}


def margin_of_safety(fair_value: float | None, current_price: float | None) -> float | None:
    if not fair_value or fair_value <= 0 or current_price is None:
        return None
    return (fair_value - current_price) / fair_value


DEFAULT_WEIGHTS = {
    "dcf": 0.35,
    "owner_earnings": 0.20,
    "earnings_multiple": 0.20,
    "ebitda_multiple": 0.15,
    "revenue_multiple": 0.10,
}
