"""Valuation orchestration (PRD 14 §6-7).

Assembles model inputs from the latest annual fundamentals + current price,
applies default assumptions (with history-derived growth) and bull/base/bear
scenario overrides, runs every model via the pure engine, and blends. Custom
assumptions from the POST endpoint override the defaults.
"""
from __future__ import annotations

from ..db import session_scope
from ..models.valuation import ValuationResult
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


def _blend_value(inp: dict, assumptions: dict, weights: dict) -> float | None:
    try:
        return engine.blended(_run_models(inp, assumptions), weights)["blended_fair_value"]
    except Exception:
        return None


def _growth_case(base: dict, growth: float) -> dict:
    a = dict(base)
    ratio = (base.get("growth_6_10") or 0) / base["growth_1_5"] if base.get("growth_1_5") else 0.5
    a["growth_1_5"] = growth
    a["growth_6_10"] = growth * ratio
    a["eps_growth"] = growth
    return a


def _grid(label: str, row_label: str, column_label: str, rows: list[tuple[str, float]], columns: list[tuple[str, float]], values: list[list[float | None]]) -> dict:
    return {
        "label": label,
        "row_label": row_label,
        "column_label": column_label,
        "rows": [{"label": label, "value": value} for label, value in rows],
        "columns": [{"label": label, "value": value} for label, value in columns],
        "values": values,
    }


def sensitivity_grids(inp: dict, base_assumptions: dict, weights: dict) -> dict:
    """Deterministic valuation sensitivities using the same model/blend path as the main result."""
    d0 = base_assumptions["discount_rate"]
    g0 = base_assumptions["growth_1_5"]
    t0 = base_assumptions["terminal_growth"]

    discount_rows = [
        (f"{(d0 + 0.02) * 100:.1f}%", d0 + 0.02),
        (f"{d0 * 100:.1f}%", d0),
        (f"{max(t0 + 0.005, d0 - 0.02) * 100:.1f}%", max(t0 + 0.005, d0 - 0.02)),
    ]
    growth_columns = [
        (f"{max(0.0, g0 * 0.5) * 100:.1f}%", max(0.0, g0 * 0.5)),
        (f"{g0 * 100:.1f}%", g0),
        (f"{max(0.0, g0 * 1.5) * 100:.1f}%", max(0.0, g0 * 1.5)),
    ]
    discount_growth_values = []
    for _, discount_rate in discount_rows:
        row = []
        for _, growth in growth_columns:
            a = _growth_case(base_assumptions, growth)
            a["discount_rate"] = discount_rate
            if a["discount_rate"] <= a["terminal_growth"]:
                row.append(None)
            else:
                row.append(_blend_value(inp, a, weights))
        discount_growth_values.append(row)

    terminal_columns = [
        (f"{max(0.0, t0 - 0.005) * 100:.1f}%", max(0.0, t0 - 0.005)),
        (f"{t0 * 100:.1f}%", t0),
        (f"{min(t0 + 0.005, d0 - 0.005) * 100:.1f}%", min(t0 + 0.005, d0 - 0.005)),
    ]
    terminal_values = []
    for _, discount_rate in discount_rows:
        row = []
        for _, terminal_growth in terminal_columns:
            a = dict(base_assumptions)
            a["discount_rate"] = discount_rate
            a["terminal_growth"] = terminal_growth
            if a["discount_rate"] <= a["terminal_growth"]:
                row.append(None)
            else:
                row.append(_blend_value(inp, a, weights))
        terminal_values.append(row)

    multiple_rows = [("0.85x", 0.85), ("1.00x", 1.0), ("1.15x", 1.15)]
    multiple_columns = [("P/E", "fair_pe"), ("EV/EBITDA", "fair_ev_ebitda"), ("EV/Sales", "fair_ev_sales")]
    multiple_values = []
    for _, mult in multiple_rows:
        row = []
        for _, key in multiple_columns:
            a = dict(base_assumptions)
            a[key] = base_assumptions[key] * mult
            row.append(_blend_value(inp, a, weights))
        multiple_values.append(row)

    return {
        "discount_growth": _grid(
            "Discount rate x FCF growth",
            "Discount rate",
            "FCF growth",
            discount_rows,
            growth_columns,
            discount_growth_values,
        ),
        "discount_terminal": _grid(
            "Discount rate x terminal growth",
            "Discount rate",
            "Terminal growth",
            discount_rows,
            terminal_columns,
            terminal_values,
        ),
        "multiples": {
            "label": "Key multiple stress",
            "row_label": "Multiple scale",
            "column_label": "Changed multiple",
            "rows": [{"label": label, "value": value} for label, value in multiple_rows],
            "columns": [{"label": label, "value": key} for label, key in multiple_columns],
            "values": multiple_values,
        },
    }


def valuation_diagnostics(models: list[dict], requested_weights: dict, applied_weights: dict, blended_fair_value: float | None) -> dict:
    rows = []
    for model in models:
        model_id = model["model"]
        fair_value = model.get("fair_value_per_share")
        raw_weight = requested_weights.get(model_id, 0.0)
        applied_weight = applied_weights.get(model_id, 0.0)
        applicable = bool(model.get("applicable") and fair_value is not None and fair_value > 0)
        if applicable and applied_weight <= 0:
            reason = "weight is zero"
        else:
            reason = model.get("reason")
        rows.append({
            "model": model_id,
            "applicable": applicable,
            "reason": reason,
            "fair_value_per_share": fair_value,
            "requested_weight": raw_weight,
            "applied_weight": applied_weight,
            "contribution": fair_value * applied_weight if fair_value is not None and applied_weight else 0.0,
            "included_in_blend": applied_weight > 0,
        })

    included_values = [row["fair_value_per_share"] for row in rows if row["included_in_blend"] and row["fair_value_per_share"] is not None]
    requested_active_sum = sum(row["requested_weight"] for row in rows if row["applicable"] and row["requested_weight"] > 0)
    return {
        "models": rows,
        "blend": {
            "applicable_count": sum(1 for row in rows if row["applicable"]),
            "excluded_count": sum(1 for row in rows if not row["applicable"]),
            "requested_active_weight": requested_active_sum,
            "renormalized": bool(rows) and abs(requested_active_sum - 1.0) > 1e-6,
            "min_component": min(included_values) if included_values else None,
            "max_component": max(included_values) if included_values else None,
            "blended_within_range": (
                blended_fair_value is not None
                and bool(included_values)
                and min(included_values) <= blended_fair_value <= max(included_values)
            ),
        },
    }


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
            "diagnostics": {"models": [], "blend": {}, "sensitivity": {}, "history_available": True},
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

    diagnostics = valuation_diagnostics(base_models, w, base_blend["applied_weights"], base_blend["blended_fair_value"])
    diagnostics["sensitivity"] = sensitivity_grids(inp, base_assumptions, w)
    diagnostics["history_available"] = True

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
        "diagnostics": diagnostics,
    }


def record_result(ticker: str, result: dict, *, weights: dict | None = None) -> dict | None:
    if result.get("blended_fair_value") is None:
        return None
    stored_weights = weights or result.get("applied_weights") or {}
    with session_scope() as session:
        latest = (
            session.query(ValuationResult)
            .filter(ValuationResult.ticker == ticker.upper())
            .order_by(ValuationResult.valuation_date.desc(), ValuationResult.id.desc())
            .first()
        )
        if latest is not None and _same_result(latest, result, stored_weights):
            return _history_row(latest)
        row = ValuationResult(
            ticker=ticker.upper(),
            current_price=result.get("current_price"),
            blended_fair_value=result.get("blended_fair_value"),
            margin_of_safety=result.get("margin_of_safety"),
            assumptions_json=result.get("assumptions") or {},
            weights_json=stored_weights,
            result_json=result,
        )
        session.add(row)
        session.flush()
        return _history_row(row)


def _same_number(a, b) -> bool:
    if a is None or b is None:
        return a is b
    return abs(a - b) < 1e-9


def _same_result(row: ValuationResult, result: dict, weights: dict) -> bool:
    return (
        _same_number(row.current_price, result.get("current_price"))
        and _same_number(row.blended_fair_value, result.get("blended_fair_value"))
        and _same_number(row.margin_of_safety, result.get("margin_of_safety"))
        and (row.assumptions_json or {}) == (result.get("assumptions") or {})
        and (row.weights_json or {}) == weights
    )


def valuation_history(ticker: str, *, limit: int = 20) -> dict:
    with session_scope() as session:
        rows = (
            session.query(ValuationResult)
            .filter(ValuationResult.ticker == ticker.upper())
            .order_by(ValuationResult.valuation_date.desc(), ValuationResult.id.desc())
            .limit(limit)
            .all()
        )
        return {"results": [_history_row(row) for row in rows]}


def _history_row(row: ValuationResult) -> dict:
    return {
        "id": row.id,
        "ticker": row.ticker,
        "valuation_date": row.valuation_date.isoformat() if row.valuation_date else None,
        "current_price": row.current_price,
        "blended_fair_value": row.blended_fair_value,
        "margin_of_safety": row.margin_of_safety,
        "assumptions": row.assumptions_json or {},
        "weights": row.weights_json or {},
    }
