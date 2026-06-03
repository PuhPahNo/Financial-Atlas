"""Valuation engine tests (PRD 07 §5, PRD 14 §10) — the highest-rigor module.

Mix of hand-computed exact checks and property/invariant checks.
"""
import math

import pytest

from app.core.errors import ValidationError
from app.valuation import engine


# --- exact hand-computed checks -------------------------------------------
def test_dividend_discount_gordon_exact():
    # next_div = 2 * 1.05 = 2.10 ; fair = 2.10 / (0.10 - 0.05) = 42.0
    r = engine.dividend_discount(dividend_per_share=2.0, growth=0.05, required_return=0.10)
    assert r["applicable"]
    assert math.isclose(r["fair_value_per_share"], 42.0, rel_tol=1e-6)


def test_earnings_multiple_zero_discount_exact():
    # future_eps = 10*(1.0)^5 = 10 ; future_price = 10*15 = 150 ; discount 0 => 150
    r = engine.earnings_multiple(eps=10.0, growth=0.0, years=5, fair_pe=15.0, discount_rate=0.0)
    assert math.isclose(r["fair_value_per_share"], 150.0, rel_tol=1e-9)


def test_margin_of_safety():
    assert math.isclose(engine.margin_of_safety(100.0, 80.0), 0.2, rel_tol=1e-9)  # undervalued
    assert engine.margin_of_safety(100.0, 120.0) < 0  # overvalued
    assert engine.margin_of_safety(None, 50.0) is None


# --- contract / edge cases -------------------------------------------------
def test_dcf_rejects_discount_le_terminal():
    with pytest.raises(ValidationError):
        engine.discounted_cash_flow(fcf0=100, growth_1_5=0.05, growth_6_10=0.03,
                                    discount_rate=0.02, terminal_growth=0.03, net_debt=0, shares=10)


def test_dcf_not_applicable_on_negative_fcf():
    r = engine.discounted_cash_flow(fcf0=-50, growth_1_5=0.05, growth_6_10=0.03,
                                    discount_rate=0.10, terminal_growth=0.02, net_debt=0, shares=10)
    assert r["applicable"] is False


def test_earnings_multiple_not_applicable_on_negative_eps():
    r = engine.earnings_multiple(eps=-1.0, growth=0.1, years=5, fair_pe=20, discount_rate=0.1)
    assert r["applicable"] is False


def test_dividend_discount_not_applicable_for_non_payer():
    r = engine.dividend_discount(dividend_per_share=0.0, growth=0.05, required_return=0.10)
    assert r["applicable"] is False


# --- property / invariant checks ------------------------------------------
def test_dcf_monotonic_in_discount_rate():
    base = dict(fcf0=100, growth_1_5=0.06, growth_6_10=0.03, terminal_growth=0.02, net_debt=0, shares=10)
    low = engine.discounted_cash_flow(discount_rate=0.08, **base)["fair_value_per_share"]
    high = engine.discounted_cash_flow(discount_rate=0.12, **base)["fair_value_per_share"]
    assert high < low  # higher discount rate => lower value


def test_blended_within_component_bounds():
    models = [
        {"model": "dcf", "applicable": True, "fair_value_per_share": 100.0},
        {"model": "earnings_multiple", "applicable": True, "fair_value_per_share": 200.0},
    ]
    weights = {"dcf": 0.5, "earnings_multiple": 0.5}
    out = engine.blended(models, weights)
    assert 100.0 <= out["blended_fair_value"] <= 200.0
    assert math.isclose(out["blended_fair_value"], 150.0, rel_tol=1e-9)


def test_blended_reweights_when_models_missing():
    # only DCF usable; its weight renormalizes to 1.0
    models = [
        {"model": "dcf", "applicable": True, "fair_value_per_share": 120.0},
        {"model": "earnings_multiple", "applicable": False, "fair_value_per_share": None},
    ]
    out = engine.blended(models, engine.DEFAULT_WEIGHTS)
    assert math.isclose(out["blended_fair_value"], 120.0, rel_tol=1e-9)
    assert math.isclose(out["applied_weights"]["dcf"], 1.0, rel_tol=1e-9)
