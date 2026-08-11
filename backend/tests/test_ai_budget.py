import pytest

from app.assistant import budget
from app.core.config import settings
from app.core.errors import BudgetExhaustedError


def _request(max_output_tokens: int = 100) -> dict:
    return {
        "model": "gpt-5.6-terra",
        "input": [{"role": "user", "content": "Analyze this company."}],
        "max_output_tokens": max_output_tokens,
    }


def test_budget_reserves_then_reconciles_reported_usage(monkeypatch):
    monkeypatch.setattr(settings, "openai_global_budget_usd", 25.0)
    monkeypatch.setattr(settings, "openai_qa_budget_usd", 10.0)
    monkeypatch.setattr(settings, "openai_usage_mode", "production")
    key = budget.reserve(_request())

    reserved = budget.status()
    assert reserved["spent_usd"] == 0
    assert reserved["reserved_usd"] > 0

    cost = budget.settle(key, {
        "id": "resp_budget_fixture",
        "usage": {
            "input_tokens": 1000,
            "input_tokens_details": {"cached_tokens": 200},
            "output_tokens": 100,
        },
    })
    # 800*2 + 200*0.2 + 100*12 = 2840 microdollars.
    assert cost == 2840
    settled = budget.status()
    assert settled["spent_usd"] == pytest.approx(0.00284)
    assert settled["reserved_usd"] == 0


def test_budget_releases_failed_request_without_spend(monkeypatch):
    monkeypatch.setattr(settings, "openai_usage_mode", "production")
    key = budget.reserve(_request())
    budget.release(key)
    current = budget.status()
    assert current["spent_usd"] == 0
    assert current["reserved_usd"] == 0


def test_global_budget_rejects_before_network_cost(monkeypatch):
    monkeypatch.setattr(settings, "openai_global_budget_usd", 0.001)
    monkeypatch.setattr(settings, "openai_qa_budget_usd", 0.001)
    monkeypatch.setattr(settings, "openai_usage_mode", "production")
    with pytest.raises(BudgetExhaustedError):
        budget.reserve(_request())
    assert budget.status()["spent_usd"] == 0


def test_qa_budget_is_separate_and_also_global(monkeypatch):
    monkeypatch.setattr(settings, "openai_global_budget_usd", 25.0)
    monkeypatch.setattr(settings, "openai_qa_budget_usd", 0.001)
    monkeypatch.setattr(settings, "openai_usage_mode", "qa")
    with pytest.raises(BudgetExhaustedError, match="QA"):
        budget.reserve(_request())
    current = budget.status()
    assert current["qa_spent_usd"] == 0
    assert current["spent_usd"] == 0


def test_reservation_estimate_dominates_max_reported_usage():
    request = _request(max_output_tokens=250)
    reserved = budget.estimate_reservation_micro(request)
    serialized_bytes = len(__import__("json").dumps(request, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    actual_upper = budget._token_cost_micro(
        input_tokens=serialized_bytes,
        cached_input_tokens=0,
        output_tokens=250,
    )
    assert reserved >= actual_upper


def test_external_qa_carryover_counts_against_both_caps(monkeypatch):
    monkeypatch.setattr(settings, "openai_global_budget_usd", 25.0)
    monkeypatch.setattr(settings, "openai_qa_budget_usd", 10.0)
    monkeypatch.setattr(settings, "openai_carryover_spend_usd", 0.203911)
    monkeypatch.setattr(settings, "openai_carryover_qa_spend_usd", 0.203911)

    current = budget.status()
    assert current["spent_usd"] == pytest.approx(0.203911)
    assert current["remaining_usd"] == pytest.approx(24.796089)
    assert current["qa_spent_usd"] == pytest.approx(0.203911)
    assert current["qa_remaining_usd"] == pytest.approx(9.796089)
