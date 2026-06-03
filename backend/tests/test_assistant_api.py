from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


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
