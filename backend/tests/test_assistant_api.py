from datetime import date

from fastapi.testclient import TestClient

from app.main import app
from app.paper_trading import accounts as account_service
from auth_helpers import authenticate

client = authenticate(TestClient(app))


def _create_strategy(name: str, category: str = "long_term") -> dict:
    response = client.post(
        "/api/v1/paper-trading/strategies",
        json={
            "category": category,
            "name": name,
            "methodology": f"{name} fixture.",
            "parameters": {"tickers": ["SPY"]},
        },
    )
    assert response.status_code == 200
    return response.json()["data"]["strategy"]


def _create_account(name: str, allocations: list[dict] | None = None) -> dict:
    response = client.post(
        "/api/v1/paper-trading/accounts",
        json={"name": name, "starting_cash": 100000, "allocations": allocations or []},
    )
    assert response.status_code == 200
    return response.json()["data"]["account"]


def _fake_backtest_result(**kwargs):
    starting_cash = kwargs["starting_cash"]
    return {
        "metrics": {"total_return": 0.12, "max_drawdown": -0.04, "win_rate": 0.58},
        "warnings": [],
        "trades": [{"date": date(2020, 1, 2), "ticker": "SPY", "side": "buy", "quantity": 10, "price": 100, "value": 1000, "reason": "fixture"}],
        "holdings": [],
        "served_by": {"fixture": True},
        "equity_curve": [
            {"date": date(2020, 1, 1), "cash": starting_cash, "equity": starting_cash, "benchmark_equity": starting_cash},
            {"date": date(2020, 12, 31), "cash": starting_cash * 1.12, "equity": starting_cash * 1.12, "benchmark_equity": starting_cash * 1.08},
        ],
    }


def test_assistant_session_and_message_persist():
    session = client.post("/api/v1/assistant/sessions", json={"title": "Test Strategy Chat"})
    assert session.status_code == 200
    session_id = session.json()["data"]["session"]["id"]

    reply = client.post(
        f"/api/v1/assistant/sessions/{session_id}/messages",
        json={"message": "Explain free cash flow and valuation for a model."},
    )
    assert reply.status_code == 200
    messages = reply.json()["data"]["messages"]
    assert messages[0]["role"] == "user"
    assert messages[-1]["role"] == "assistant"


def test_assistant_create_strategy_requires_confirmation():
    session_id = client.post("/api/v1/assistant/sessions", json={"title": "Test Action Chat"}).json()["data"]["session"]["id"]
    reply = client.post(
        f"/api/v1/assistant/sessions/{session_id}/messages",
        json={"message": "Create a strategy named AI FCF Test for AAPL and MSFT."},
    )
    data = reply.json()["data"]
    assert data["pending_actions"]
    action = data["pending_actions"][0]
    assert action["action"] == "create_strategy"

    confirmed = client.post(f"/api/v1/assistant/actions/{action['id']}/confirm", json={})
    assert confirmed.status_code == 200
    assert confirmed.json()["data"]["result"]["strategy"]["name"] == "AI FCF Test"


def test_assistant_assign_strategy_to_trader_requires_confirmation():
    strategy = client.post(
        "/api/v1/paper-trading/strategies",
        json={
            "category": "risk_rotation",
            "name": "Assistant Assign Strategy",
            "methodology": "Assistant assignment fixture.",
            "parameters": {"tickers": ["SPY"]},
        },
    ).json()["data"]["strategy"]
    account = client.post(
        "/api/v1/paper-trading/accounts",
        json={"name": "Assistant Assign Trader", "starting_cash": 100000, "allocations": []},
    ).json()["data"]["account"]

    session_id = client.post("/api/v1/assistant/sessions", json={"title": "Test Assign Chat"}).json()["data"]["session"]["id"]
    reply = client.post(
        f"/api/v1/assistant/sessions/{session_id}/messages",
        json={"message": "Assign Assistant Assign Strategy to Assistant Assign Trader at 15%"},
    )
    data = reply.json()["data"]
    assert data["pending_actions"]
    action = data["pending_actions"][0]
    assert action["action"] == "assign_strategy_to_account"
    assert action["payload"]["account_name"] == "Assistant Assign Trader"

    confirmed = client.post(f"/api/v1/assistant/actions/{action['id']}/confirm", json={})
    assert confirmed.status_code == 200
    result = confirmed.json()["data"]["result"]
    assert result["assigned"]["strategy_id"] == strategy["id"]
    assert result["assigned"]["account_id"] == account["id"]
    assert result["assigned"]["weight"] == 15
    assert result["account"]["allocations"][0]["weight"] == 15


def test_assistant_lists_profiles_as_read_only():
    _create_account("Assistant Profile Reader")

    session_id = client.post("/api/v1/assistant/sessions", json={"title": "Test Profiles Chat"}).json()["data"]["session"]["id"]
    reply = client.post(
        f"/api/v1/assistant/sessions/{session_id}/messages",
        json={"message": "List my trader profiles"},
    )
    data = reply.json()["data"]
    assert data["pending_actions"] == []
    assert "Assistant Profile Reader" in data["messages"][-1]["content"]
    assert data["messages"][-1]["tool_calls"][0]["tool"] == "list_accounts"


def test_assistant_account_performance_is_read_only(monkeypatch):
    strategy = _create_strategy("Assistant Performance Strategy")
    _create_account("Assistant Performance Trader", [{"strategy_id": strategy["id"], "weight": 50}])

    def fake_backtest(**kwargs):
        starting_cash = kwargs["starting_cash"]
        return {
            "metrics": {},
            "warnings": [],
            "trades": [],
            "holdings": [],
            "equity_curve": [
                {"date": date(2020, 1, 1), "cash": 0, "equity": starting_cash, "benchmark_equity": starting_cash},
                {"date": date(2020, 1, 2), "cash": 0, "equity": starting_cash + 1000, "benchmark_equity": starting_cash + 500},
            ],
        }

    monkeypatch.setattr(account_service, "execute_backtest", fake_backtest)

    session_id = client.post("/api/v1/assistant/sessions", json={"title": "Test Performance Chat"}).json()["data"]["session"]["id"]
    reply = client.post(
        f"/api/v1/assistant/sessions/{session_id}/messages",
        json={"message": "Show risk and performance for Assistant Performance Trader profile"},
    )
    data = reply.json()["data"]
    assert data["pending_actions"] == []
    assert "returned +1.0%" in data["messages"][-1]["content"]
    assert data["messages"][-1]["tool_calls"][0]["tool"] == "account_performance"


def test_assistant_clone_strategy_requires_confirmation_and_human_payload():
    source = _create_strategy("Assistant Clone Source")

    session_id = client.post("/api/v1/assistant/sessions", json={"title": "Test Clone Chat"}).json()["data"]["session"]["id"]
    reply = client.post(
        f"/api/v1/assistant/sessions/{session_id}/messages",
        json={"message": "Clone strategy Assistant Clone Source"},
    )
    data = reply.json()["data"]
    action = data["pending_actions"][0]
    assert action["action"] == "clone_strategy"
    assert action["payload"]["strategy_id"] == source["id"]
    assert action["payload"]["action_summary"] == "Clone model “Assistant Clone Source”"
    assert "editable" in action["payload"]["action_details"]

    confirmed = client.post(f"/api/v1/assistant/actions/{action['id']}/confirm", json={})
    assert confirmed.status_code == 200
    assert confirmed.json()["data"]["result"]["strategy"]["name"] == "Assistant Clone Source Copy"


def test_assistant_rebalance_account_requires_confirmation():
    first = _create_strategy("Assistant Rebalance A")
    _create_strategy("Assistant Rebalance B")
    _create_account("Assistant Rebalance Trader", [{"strategy_id": first["id"], "weight": 10}])

    session_id = client.post("/api/v1/assistant/sessions", json={"title": "Test Rebalance Chat"}).json()["data"]["session"]["id"]
    reply = client.post(
        f"/api/v1/assistant/sessions/{session_id}/messages",
        json={"message": "Rebalance Assistant Rebalance Trader to 40% Assistant Rebalance A and 20% Assistant Rebalance B"},
    )
    data = reply.json()["data"]
    action = data["pending_actions"][0]
    assert action["action"] == "rebalance_account"
    assert action["payload"]["action_summary"] == "Rebalance “Assistant Rebalance Trader”"
    assert "Assistant Rebalance B" in action["payload"]["action_details"]

    confirmed = client.post(f"/api/v1/assistant/actions/{action['id']}/confirm", json={})
    assert confirmed.status_code == 200
    allocations = confirmed.json()["data"]["result"]["account"]["allocations"]
    assert {row["name"]: row["weight"] for row in allocations} == {"Assistant Rebalance A": 40, "Assistant Rebalance B": 20}


def test_assistant_rebalance_preserves_unmentioned_sleeves():
    """Naming only some sleeves must NOT liquidate the rest — the assistant merges the
    named weights onto the account's current allocation (audit L5)."""
    first = _create_strategy("Assistant Rebalance A")
    second = _create_strategy("Assistant Rebalance B")
    _create_account("Assistant Rebalance Trader",
                    [{"strategy_id": first["id"], "weight": 10}, {"strategy_id": second["id"], "weight": 10}])

    session_id = client.post("/api/v1/assistant/sessions", json={"title": "Test Rebalance Chat"}).json()["data"]["session"]["id"]
    reply = client.post(
        f"/api/v1/assistant/sessions/{session_id}/messages",
        json={"message": "Rebalance Assistant Rebalance Trader to 40% Assistant Rebalance A"},
    )
    action = reply.json()["data"]["pending_actions"][0]
    assert "keeping Assistant Rebalance B" in action["payload"]["action_details"]

    confirmed = client.post(f"/api/v1/assistant/actions/{action['id']}/confirm", json={})
    allocations = confirmed.json()["data"]["result"]["account"]["allocations"]
    # A rebalanced to 40, B kept at 10 — not dropped to cash.
    assert {row["name"]: row["weight"] for row in allocations} == {"Assistant Rebalance A": 40, "Assistant Rebalance B": 10}


def test_copilot_can_create_backtest_and_assign_generated_model(monkeypatch):
    _create_account("Assistant Generated Trader")

    monkeypatch.setattr("app.paper_trading.service.execute_backtest", _fake_backtest_result)

    session_id = client.post("/api/v1/assistant/sessions", json={"title": "Test Copilot Workflow Chat"}).json()["data"]["session"]["id"]
    created = client.post(
        f"/api/v1/assistant/sessions/{session_id}/messages",
        json={"message": "Create a strategy named Assistant Generated Model for SPY"},
    ).json()["data"]
    create_action = created["pending_actions"][0]
    source_message_id = created["messages"][0]["id"]
    assert create_action["action"] == "create_strategy"
    assert create_action["payload"]["action_summary"] == "Create model “Assistant Generated Model”"
    assert create_action["payload"]["_assistant"]["source_message_id"] == source_message_id
    confirmed_create = client.post(f"/api/v1/assistant/actions/{create_action['id']}/confirm", json={})
    strategy = confirmed_create.json()["data"]["result"]["strategy"]
    assert strategy["name"] == "Assistant Generated Model"
    assert strategy["metrics"]["_assistant"]["source_message_id"] == source_message_id
    action_log = confirmed_create.json()["data"]["actions"][0]
    assert action_log["status"] == "confirmed"
    assert action_log["source_message_id"] == source_message_id
    assert action_log["result_ref"] == {"type": "strategy", "id": strategy["id"], "name": "Assistant Generated Model"}

    backtested = client.post(
        f"/api/v1/assistant/sessions/{session_id}/messages",
        json={"message": "Backtest Assistant Generated Model over 2020"},
    ).json()["data"]
    assert backtested["pending_actions"] == []
    assert "total return +12.0%" in backtested["messages"][-1]["content"]
    assert backtested["messages"][-1]["tool_calls"][0]["tool"] == "run_backtest"
    run_ref = backtested["messages"][-1]["tool_calls"][0]["result_ref"]
    saved_run = client.get(f"/api/v1/backtests/{run_ref['id']}").json()["data"]["run"]
    assert saved_run["inputs"]["assistant_context"]["created_by"] == "atlas_copilot"

    assigned = client.post(
        f"/api/v1/assistant/sessions/{session_id}/messages",
        json={"message": "Assign Assistant Generated Model to Assistant Generated Trader at 25%"},
    ).json()["data"]
    assign_action = assigned["pending_actions"][0]
    assert assign_action["action"] == "assign_strategy_to_account"
    assert assign_action["payload"]["action_summary"] == "Assign “Assistant Generated Model” to “Assistant Generated Trader” at 25.0%"
    confirmed_assign = client.post(f"/api/v1/assistant/actions/{assign_action['id']}/confirm", json={})
    assert confirmed_assign.status_code == 200
    assert confirmed_assign.json()["data"]["result"]["assigned"]["strategy_id"] == strategy["id"]


def test_copilot_multistep_plan_resumes_and_requires_separate_assignment_confirmation(monkeypatch):
    _create_account("Assistant Orchestrated Trader")
    monkeypatch.setattr("app.paper_trading.service.execute_backtest", _fake_backtest_result)

    session_id = client.post("/api/v1/assistant/sessions", json={"title": "Test Orchestration Chat"}).json()["data"]["session"]["id"]
    planned = client.post(
        f"/api/v1/assistant/sessions/{session_id}/messages",
        json={"message": "Create a strategy named Assistant Orchestrated Model for SPY, backtest it over 2020, then assign it to Assistant Orchestrated Trader at 25%"},
    ).json()["data"]
    create_action = planned["pending_actions"][0]
    assert create_action["action"] == "create_strategy"
    assert create_action["payload"]["plan"]["status"] == "awaiting_create_confirmation"
    assert "Confirm below to create only the model" in planned["messages"][-1]["content"]

    confirmed_create = client.post(f"/api/v1/assistant/actions/{create_action['id']}/confirm", json={}).json()["data"]
    assert confirmed_create["pending_actions"] == []
    assert "Say “continue”" in confirmed_create["messages"][-1]["content"]

    resumed = client.post(
        f"/api/v1/assistant/sessions/{session_id}/messages",
        json={"message": "continue"},
    ).json()["data"]
    assert "total return +12.0%" in resumed["messages"][-1]["content"]
    assert "separate confirmation" in resumed["messages"][-1]["content"]
    assert resumed["messages"][-1]["tool_calls"][0]["tool"] == "run_backtest"
    assign_action = resumed["pending_actions"][0]
    assert assign_action["action"] == "assign_strategy_to_account"
    assert assign_action["payload"]["action_summary"] == "Assign “Assistant Orchestrated Model” to “Assistant Orchestrated Trader” at 25.0%"

    confirmed_assign = client.post(f"/api/v1/assistant/actions/{assign_action['id']}/confirm", json={}).json()["data"]
    assert "plan is complete" in confirmed_assign["messages"][-1]["content"]
    assert confirmed_assign["result"]["assigned"]["account_name"] == "Assistant Orchestrated Trader"
    memory = client.get(f"/api/v1/assistant/sessions/{session_id}").json()["data"]["session"]["memory"]
    assert memory["status"] == "complete"
    assert memory["models"][0]["name"] == "Assistant Orchestrated Model"
    assert memory["backtests"][0]["type"] == "backtest_run"
    assert memory["assignments"][0]["account_name"] == "Assistant Orchestrated Trader"
    assert all(action.get("source_message_id") for action in memory["actions"])


def test_copilot_multistep_assignment_rejection_does_not_change_account(monkeypatch):
    account = _create_account("Assistant Orchestrated Trader")
    monkeypatch.setattr("app.paper_trading.service.execute_backtest", _fake_backtest_result)

    session_id = client.post("/api/v1/assistant/sessions", json={"title": "Test Orchestration Reject Chat"}).json()["data"]["session"]["id"]
    planned = client.post(
        f"/api/v1/assistant/sessions/{session_id}/messages",
        json={"message": "Create a strategy named Assistant Orchestrated Model for SPY, backtest it over 2020, then assign it to Assistant Orchestrated Trader at 25%"},
    ).json()["data"]
    create_action = planned["pending_actions"][0]
    client.post(f"/api/v1/assistant/actions/{create_action['id']}/confirm", json={})
    resumed = client.post(f"/api/v1/assistant/sessions/{session_id}/messages", json={"message": "continue"}).json()["data"]
    assign_action = resumed["pending_actions"][0]

    rejected = client.post(f"/api/v1/assistant/actions/{assign_action['id']}/reject", json={}).json()["data"]
    assert "did not run that plan step" in rejected["messages"][-1]["content"]
    fresh_account = client.get(f"/api/v1/paper-trading/accounts/{account['id']}").json()["data"]["account"]
    assert fresh_account["allocations"] == []


def test_copilot_multistep_failed_backtest_can_retry(monkeypatch):
    _create_account("Assistant Retry Trader")
    attempts = {"count": 0}

    def flaky_backtest(**kwargs):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("fixture outage")
        return _fake_backtest_result(**kwargs)

    monkeypatch.setattr("app.paper_trading.service.execute_backtest", flaky_backtest)

    session_id = client.post("/api/v1/assistant/sessions", json={"title": "Test Orchestration Retry Chat"}).json()["data"]["session"]["id"]
    planned = client.post(
        f"/api/v1/assistant/sessions/{session_id}/messages",
        json={"message": "Create a strategy named Assistant Retry Model for SPY, backtest it over 2020, then assign it to Assistant Retry Trader at 25%"},
    ).json()["data"]
    create_action = planned["pending_actions"][0]
    client.post(f"/api/v1/assistant/actions/{create_action['id']}/confirm", json={})

    failed = client.post(f"/api/v1/assistant/sessions/{session_id}/messages", json={"message": "continue"}).json()["data"]
    assert "fixture outage" in failed["messages"][-1]["content"]
    assert failed["pending_actions"] == []

    retried = client.post(f"/api/v1/assistant/sessions/{session_id}/messages", json={"message": "retry"}).json()["data"]
    assert "total return +12.0%" in retried["messages"][-1]["content"]
    assert retried["pending_actions"][0]["action"] == "assign_strategy_to_account"
