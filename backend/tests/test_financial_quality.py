from app.services.financials import cash_flow_scorecard


def test_cash_flow_scorecard_flags_strong_cash_quality():
    scorecard = cash_flow_scorecard([
        {
            "fiscal_year": 2025,
            "free_cash_flow": 140,
            "fcf_conversion": 0.95,
            "fcf_margin": 0.24,
            "payout_vs_fcf": 0.55,
            "capital_returned": 77,
            "reinvestment_rate": 0.3,
            "capex_pct_revenue": 0.06,
            "sbc_pct_ocf": 0.03,
            "net_debt": -20,
            "net_debt_to_fcf": -0.14,
        },
        {"fiscal_year": 2021, "free_cash_flow": 90},
    ])

    cards = {card["id"]: card for card in scorecard["cards"]}
    assert scorecard["overall_score"] >= 80
    assert cards["cash_conversion"]["tone"] == "positive"
    assert cards["capital_allocation"]["tone"] == "positive"
    assert cards["sbc_load"]["tone"] == "positive"
    assert cards["balance_sheet"]["tone"] == "positive"
    assert cards["fcf_growth"]["tone"] == "positive"


def test_cash_flow_scorecard_flags_weak_conversion_and_uncovered_payout():
    scorecard = cash_flow_scorecard([
        {
            "fiscal_year": 2025,
            "free_cash_flow": 80,
            "fcf_conversion": 0.35,
            "fcf_margin": 0.04,
            "payout_vs_fcf": 1.5,
            "capital_returned": 120,
            "reinvestment_rate": 1.1,
            "capex_pct_revenue": 0.2,
            "sbc_pct_ocf": 0.22,
            "net_debt": 400,
            "net_debt_to_fcf": 5.0,
        },
        {"fiscal_year": 2021, "free_cash_flow": 120},
    ])

    cards = {card["id"]: card for card in scorecard["cards"]}
    assert scorecard["overall_score"] <= 40
    assert cards["cash_conversion"]["tone"] == "negative"
    assert cards["capital_allocation"]["tone"] == "negative"
    assert cards["reinvestment"]["tone"] == "negative"
    assert cards["sbc_load"]["tone"] == "negative"
    assert cards["balance_sheet"]["tone"] == "negative"
    assert cards["fcf_growth"]["tone"] == "negative"


def test_cash_flow_scorecard_handles_missing_inputs_without_fake_scores():
    scorecard = cash_flow_scorecard([{"fiscal_year": 2025, "free_cash_flow": None}])

    cards = {card["id"]: card for card in scorecard["cards"]}
    assert scorecard["overall_score"] is None
    assert cards["cash_conversion"]["score"] is None
    assert cards["capital_allocation"]["score"] is None
    assert cards["sbc_load"]["score"] is None
    assert cards["balance_sheet"]["score"] is None
