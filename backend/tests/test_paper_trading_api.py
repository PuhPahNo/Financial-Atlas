from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_seeded_categories_include_models():
    res = client.get("/api/v1/paper-trading/categories")
    assert res.status_code == 200
    categories = res.json()["data"]["categories"]
    assert categories
    assert all(len(category["strategies"]) >= 3 for category in categories)


def test_strategy_crud_clone_and_archive():
    created = client.post(
        "/api/v1/paper-trading/strategies",
        json={
            "category": "long_term",
            "name": "Test Quality Clone",
            "description": "Looks for resilient cash generators.",
            "methodology": "Rank by FCF yield and quality.",
            "parameters": {"tickers": ["AAPL"], "lookback_days": 120},
        },
    )
    assert created.status_code == 200
    strategy = created.json()["data"]["strategy"]

    updated = client.put(
        f"/api/v1/paper-trading/strategies/{strategy['id']}",
        json={"name": "Updated Quality Clone", "parameters": {"tickers": ["MSFT"], "lookback_days": 90}},
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["strategy"]["name"] == "Updated Quality Clone"

    cloned = client.post(f"/api/v1/paper-trading/strategies/{strategy['id']}/clone")
    assert cloned.status_code == 200
    assert cloned.json()["data"]["strategy"]["origin"] == "user"

    deleted = client.delete(f"/api/v1/paper-trading/strategies/{strategy['id']}")
    assert deleted.status_code == 200
    assert deleted.json()["data"]["deleted"] == strategy["id"]


def test_backtest_fixture_strategy_persists_trades_and_equity():
    strategy = client.post(
        "/api/v1/paper-trading/strategies",
        json={
            "category": "short_term",
            "name": "Test Fixture Momentum",
            "description": "Buys fixture trend.",
            "methodology": "Fixture strategy for API contract.",
            "parameters": {"tickers": ["AAA"], "lookback_days": 2},
        },
    ).json()["data"]["strategy"]

    res = client.post(
        "/api/v1/backtests",
        json={
            "strategy_id": strategy["id"],
            "tickers": ["AAA"],
            "start_date": "2020-01-01",
            "end_date": "2020-01-05",
            "starting_cash": 1000,
            "use_fixture_data": True,
        },
    )
    assert res.status_code == 200
    run = res.json()["data"]["run"]
    assert run["metrics"]["total_return"] != 0
    assert run["trades"]
    assert run["equity_curve"]


def test_rule_based_backtest_enters_on_signal_and_takes_profit():
    strategy = client.post(
        "/api/v1/paper-trading/strategies",
        json={
            "category": "risk_rotation",
            "name": "Test Signal Rule",
            "description": "Buys on a new high, exits on a quick profit.",
            "methodology": "Signal-driven rule strategy for the engine contract.",
            "parameters": {
                "tickers": ["AAA"],
                "rules": {
                    "instrument": "AAA",
                    "direction": "long",
                    "signal": {"type": "new_high", "reference": "AAA"},
                    "take_profit_pct": 0.05,
                    "stop_loss_pct": 0.5,
                },
            },
        },
    ).json()["data"]["strategy"]

    res = client.post(
        "/api/v1/backtests",
        json={
            "strategy_id": strategy["id"],
            "tickers": ["AAA"],
            "start_date": "2020-01-01",
            "end_date": "2020-01-05",
            "starting_cash": 10000,
            "use_fixture_data": True,
        },
    )
    assert res.status_code == 200
    run = res.json()["data"]["run"]
    sides = [t["side"] for t in run["trades"]]
    reasons = " ".join(t["reason"] for t in run["trades"])
    assert "buy" in sides  # signal opened a position
    assert "new high" in reasons  # entry was driven by the signal, not buy-and-hold
    assert "take-profit" in reasons  # the +5% exit fired on the deterministic fixture
    assert len(run["equity_curve"]) == 5


def test_create_paper_portfolio_from_strategy():
    strategy = client.post(
        "/api/v1/paper-trading/strategies",
        json={
            "category": "income_quality",
            "name": "Test Income Portfolio",
            "description": "Income test.",
            "methodology": "Fixture portfolio.",
            "parameters": {"tickers": ["AAA"]},
        },
    ).json()["data"]["strategy"]

    res = client.post(
        "/api/v1/paper-trading/portfolios",
        json={"strategy_id": strategy["id"], "name": "Fixture Portfolio", "starting_cash": 25000},
    )
    assert res.status_code == 200
    portfolio = res.json()["data"]["portfolio"]
    assert portfolio["cash"] == 25000
    assert portfolio["positions"] == []


def test_run_paper_portfolio_creates_order_fill_and_position():
    strategy = client.post(
        "/api/v1/paper-trading/strategies",
        json={
            "category": "risk_rotation",
            "name": "Test Run Portfolio",
            "description": "Run test.",
            "methodology": "Fixture paper run.",
            "parameters": {"tickers": ["AAA"], "allocation_pct": 0.5},
        },
    ).json()["data"]["strategy"]
    portfolio = client.post(
        "/api/v1/paper-trading/portfolios",
        json={"strategy_id": strategy["id"], "name": "Runnable Portfolio", "starting_cash": 1000},
    ).json()["data"]["portfolio"]

    res = client.post(f"/api/v1/paper-trading/portfolios/{portfolio['id']}/run", json={"use_fixture_data": True})
    assert res.status_code == 200
    updated = res.json()["data"]["portfolio"]
    assert updated["cash"] < 1000
    assert updated["positions"][0]["ticker"] == "AAA"
    assert updated["orders"][0]["status"] == "filled"
    assert updated["orders"][0]["fills"][0]["source"] == "fixture"


def test_trader_account_crud_and_allocation_validation():
    strat = client.post(
        "/api/v1/paper-trading/strategies",
        json={"category": "long_term", "name": "Acct Test Strategy", "methodology": "x",
              "parameters": {"tickers": ["AAA"]}},
    ).json()["data"]["strategy"]

    created = client.post(
        "/api/v1/paper-trading/accounts",
        json={"name": "Test Trader", "emoji": "🐳", "starting_cash": 50000,
              "allocations": [{"strategy_id": strat["id"], "weight": 40}]},
    )
    assert created.status_code == 200
    acc = created.json()["data"]["account"]
    assert acc["invested_pct"] == 40 and acc["cash_pct"] == 60
    assert acc["allocations"][0]["dollars"] == 20000

    # over-allocation is rejected
    bad = client.post(
        "/api/v1/paper-trading/accounts",
        json={"name": "Over", "starting_cash": 1000,
              "allocations": [{"strategy_id": strat["id"], "weight": 140}]},
    )
    assert bad.status_code == 422  # pydantic ge/le on weight

    listed = client.get("/api/v1/paper-trading/accounts").json()["data"]["accounts"]
    assert any(a["id"] == acc["id"] for a in listed)

    updated = client.put(
        f"/api/v1/paper-trading/accounts/{acc['id']}",
        json={"name": "Renamed Trader", "allocations": [{"strategy_id": strat["id"], "weight": 75}]},
    ).json()["data"]["account"]
    assert updated["name"] == "Renamed Trader" and updated["invested_pct"] == 75

    deleted = client.delete(f"/api/v1/paper-trading/accounts/{acc['id']}")
    assert deleted.status_code == 200 and deleted.json()["data"]["deleted"] == acc["id"]
