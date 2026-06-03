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


def _net_debt(balance) -> float | None:
    if balance is None or balance.total_debt is None:
        return None
    cash = (balance.cash_and_equivalents or 0) + (balance.short_term_investments or 0)
    return balance.total_debt - cash


def _tone(value: float | None, good: float, caution: float, *, higher_is_better: bool = True) -> str:
    if value is None:
        return "neutral"
    if higher_is_better:
        if value >= good:
            return "positive"
        if value >= caution:
            return "neutral"
        return "negative"
    if value <= good:
        return "positive"
    if value <= caution:
        return "neutral"
    return "negative"


def _score(value: float | None, good: float, caution: float, *, higher_is_better: bool = True) -> int | None:
    if value is None:
        return None
    tone = _tone(value, good, caution, higher_is_better=higher_is_better)
    return {"positive": 85, "neutral": 60, "negative": 30}[tone]


def _driver(label: str, value, status: str, reason: str) -> dict:
    return {"label": label, "value": value, "status": status, "reason": reason}


def _cagr(rows: list[dict], field: str) -> float | None:
    valid = [
        (row["fiscal_year"], row[field])
        for row in rows
        if row.get("fiscal_year") is not None and row.get(field) is not None and row[field] > 0
    ]
    if len(valid) < 2:
        return None
    valid.sort(key=lambda item: item[0])
    first_year, first_value = valid[0]
    last_year, last_value = valid[-1]
    years = last_year - first_year
    if years <= 0 or first_value <= 0:
        return None
    return (last_value / first_value) ** (1 / years) - 1


def _quality_card(
    card_id: str,
    label: str,
    score: int | None,
    tone: str,
    summary: str,
    drivers: list[dict],
) -> dict:
    return {
        "id": card_id,
        "label": label,
        "score": score,
        "tone": tone,
        "summary": summary,
        "drivers": drivers,
    }


def cash_flow_scorecard(periods: list[dict]) -> dict:
    if not periods:
        return {"overall_score": None, "cards": []}

    latest = periods[0]
    conversion = latest.get("fcf_conversion")
    margin = latest.get("fcf_margin")
    conversion_score = _score(conversion, 0.9, 0.6)
    margin_tone = _tone(margin, 0.2, 0.1)
    cash_tone = _tone(conversion, 0.9, 0.6)
    cash_summary = (
        "Strong earnings-to-cash conversion."
        if cash_tone == "positive" else
        "Acceptable cash conversion; watch the margin trend."
        if cash_tone == "neutral" else
        "Weak conversion from accounting profit into free cash flow."
    )

    payout = latest.get("payout_vs_fcf")
    payout_score = _score(payout, 1.0, 1.25, higher_is_better=False)
    payout_tone = _tone(payout, 1.0, 1.25, higher_is_better=False)
    allocation_summary = (
        "Capital returns are covered by free cash flow."
        if payout_tone == "positive" else
        "Capital returns are close to free cash flow capacity."
        if payout_tone == "neutral" else
        "Capital returns exceed recent free cash flow."
    )

    reinvestment = latest.get("reinvestment_rate")
    capex_revenue = latest.get("capex_pct_revenue")
    reinvestment_score = None
    if reinvestment is not None:
        if reinvestment <= 0.75:
            reinvestment_score = 75
        elif reinvestment <= 1.0:
            reinvestment_score = 55
        else:
            reinvestment_score = 35
    reinvestment_tone = (
        "positive" if reinvestment_score is not None and reinvestment_score >= 70 else
        "neutral" if reinvestment_score is not None and reinvestment_score >= 50 else
        "negative" if reinvestment_score is not None else
        "neutral"
    )

    sbc = latest.get("sbc_pct_ocf")
    sbc_score = _score(sbc, 0.05, 0.15, higher_is_better=False)
    sbc_tone = _tone(sbc, 0.05, 0.15, higher_is_better=False)
    sbc_summary = (
        "Stock-based compensation is modest relative to operating cash flow."
        if sbc_tone == "positive" else
        "Stock-based compensation is meaningful but not extreme."
        if sbc_tone == "neutral" else
        "Stock-based compensation consumes a high share of operating cash flow."
    )

    net_debt = latest.get("net_debt")
    net_debt_to_fcf = latest.get("net_debt_to_fcf")
    if net_debt is not None and net_debt <= 0:
        balance_score = 90
        balance_tone = "positive"
        balance_summary = "Net cash balance sheet supports cash-flow durability."
    else:
        balance_score = _score(net_debt_to_fcf, 1.0, 3.0, higher_is_better=False)
        balance_tone = _tone(net_debt_to_fcf, 1.0, 3.0, higher_is_better=False)
        balance_summary = (
            "Net debt is modest relative to recent free cash flow."
            if balance_tone == "positive" else
            "Net debt is material but within a monitorable range."
            if balance_tone == "neutral" else
            "Net debt is heavy relative to recent free cash flow."
        )

    fcf_growth = _cagr(periods[:8], "free_cash_flow")
    growth_score = _score(fcf_growth, 0.1, 0.0)
    growth_tone = _tone(fcf_growth, 0.1, 0.0)
    growth_summary = (
        "Free cash flow has compounded at a healthy rate."
        if growth_tone == "positive" else
        "Free cash flow is roughly stable across the available history."
        if growth_tone == "neutral" else
        "Free cash flow has contracted across the available history."
    )

    cards = [
        _quality_card(
            "cash_conversion",
            "Cash conversion",
            conversion_score,
            cash_tone,
            cash_summary,
            [
                _driver("FCF conversion", conversion, cash_tone, "FCF divided by net income."),
                _driver("FCF margin", margin, margin_tone, "FCF divided by revenue."),
            ],
        ),
        _quality_card(
            "capital_allocation",
            "Capital allocation",
            payout_score,
            payout_tone,
            allocation_summary,
            [
                _driver("Payout vs FCF", payout, payout_tone, "Buybacks plus dividends divided by FCF."),
                _driver("Capital returned", latest.get("capital_returned"), "neutral", "Buybacks plus dividends."),
            ],
        ),
        _quality_card(
            "reinvestment",
            "Reinvestment load",
            reinvestment_score,
            reinvestment_tone,
            "Capex demands are manageable relative to operating cash flow."
            if reinvestment_tone == "positive" else
            "Reinvestment consumes a notable share of operating cash flow."
            if reinvestment_tone == "neutral" else
            "Capex consumes most or all recent operating cash flow.",
            [
                _driver("Reinvestment rate", reinvestment, reinvestment_tone, "Capex divided by operating cash flow."),
                _driver("CapEx / revenue", capex_revenue, "neutral", "Capex divided by revenue."),
            ],
        ),
        _quality_card(
            "sbc_load",
            "SBC load",
            sbc_score,
            sbc_tone,
            sbc_summary,
            [_driver("SBC / OCF", sbc, sbc_tone, "Stock-based compensation divided by operating cash flow.")],
        ),
        _quality_card(
            "balance_sheet",
            "Balance sheet",
            balance_score,
            balance_tone,
            balance_summary,
            [
                _driver("Net debt", net_debt, balance_tone, "Total debt minus cash and short-term investments."),
                _driver("Net debt / FCF", net_debt_to_fcf, balance_tone, "Net debt divided by recent free cash flow."),
            ],
        ),
        _quality_card(
            "fcf_growth",
            "FCF growth",
            growth_score,
            growth_tone,
            growth_summary,
            [_driver("FCF CAGR", fcf_growth, growth_tone, "Compound growth across available positive FCF years.")],
        ),
    ]

    scores = [card["score"] for card in cards if card["score"] is not None]
    return {
        "overall_score": round(sum(scores) / len(scores)) if scores else None,
        "cards": cards,
    }


def cash_flow_analysis(ticker: str, period: Period = Period.ANNUAL) -> dict:
    """Derived FCF metric series, one entry per fiscal period (PRD 13)."""
    income, _ = run_chain("income", "get_income_statements", ticker, period=period)
    try:
        balance, _ = run_chain("balance", "get_balance_sheets", ticker, period=period)
    except Exception:
        balance = []
    cashflow, served_by = run_chain("cashflow", "get_cash_flows", ticker, period=period)
    income_by_key = {(s.fiscal_year, s.period): s for s in income}
    balance_by_key = {(s.fiscal_year, s.period): s for s in balance}

    periods = []
    for cf in cashflow:  # already sorted newest-first
        inc = income_by_key.get((cf.fiscal_year, cf.period))
        bal = balance_by_key.get((cf.fiscal_year, cf.period))
        revenue = inc.revenue if inc else None
        net_income = inc.net_income if inc else None
        shares = (inc.weighted_average_shares_diluted or inc.weighted_average_shares) if inc else None
        net_debt = _net_debt(bal)

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
            "net_debt": net_debt,
            "net_debt_to_fcf": _safe_div(net_debt, fcf) if (fcf or 0) > 0 else None,
        })
    return {"periods": periods, "scorecard": cash_flow_scorecard(periods), "served_by": served_by}
