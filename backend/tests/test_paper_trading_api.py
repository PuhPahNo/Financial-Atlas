from fastapi.testclient import TestClient

from app.main import app
from app.paper_trading import accounts as account_service
from auth_helpers import authenticate

client = authenticate(TestClient(app))


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


def test_full_paper_trading_regression_create_save_backtest_assign_archive():
    created = client.post(
        "/api/v1/paper-trading/strategies",
        json={
            "category": "short_term",
            "name": "Test Full QA Strategy",
            "description": "Full regression strategy.",
            "methodology": "Uses fixture prices for repeatable QA.",
            "parameters": {"tickers": ["AAA"], "lookback_days": 2},
        },
    )
    assert created.status_code == 200
    strategy = created.json()["data"]["strategy"]

    saved = client.put(
        f"/api/v1/paper-trading/strategies/{strategy['id']}",
        json={"name": "Test Full QA Strategy Saved", "parameters": {"tickers": ["AAA"], "lookback_days": 3}},
    )
    assert saved.status_code == 200
    strategy = saved.json()["data"]["strategy"]
    assert strategy["parameters"]["lookback_days"] == 3

    backtest = client.post(
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
    assert backtest.status_code == 200
    run = backtest.json()["data"]["run"]
    assert run["strategy_snapshot"]["name"] == "Test Full QA Strategy Saved"
    assert run["trades"]

    account = client.post(
        "/api/v1/paper-trading/accounts",
        json={"name": "Test Full QA Trader", "starting_cash": 25000, "allocations": [{"strategy_id": strategy["id"], "weight": 40}]},
    )
    assert account.status_code == 200
    account_id = account.json()["data"]["account"]["id"]
    assert account.json()["data"]["account"]["allocations"][0]["name"] == "Test Full QA Strategy Saved"

    archived = client.delete(f"/api/v1/paper-trading/strategies/{strategy['id']}")
    assert archived.status_code == 200
    account_after_archive = client.get(f"/api/v1/paper-trading/accounts/{account_id}")
    assert account_after_archive.status_code == 200
    allocation = account_after_archive.json()["data"]["account"]["allocations"][0]
    assert allocation["strategy_status"] == "archived"
    assert allocation["archived"] is True

    deleted_account = client.delete(f"/api/v1/paper-trading/accounts/{account_id}")
    assert deleted_account.status_code == 200


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


def test_backtest_run_preserves_strategy_snapshot_after_model_edit():
    strategy = client.post(
        "/api/v1/paper-trading/strategies",
        json={
            "category": "short_term",
            "name": "Test Snapshot Strategy",
            "description": "Snapshot test.",
            "methodology": "Fixture strategy for immutable run inputs.",
            "parameters": {"tickers": ["AAA"], "lookback_days": 2},
        },
    ).json()["data"]["strategy"]

    run_res = client.post(
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
    assert run_res.status_code == 200
    run_id = run_res.json()["data"]["run"]["id"]

    client.put(
        f"/api/v1/paper-trading/strategies/{strategy['id']}",
        json={"parameters": {"tickers": ["BBB"], "lookback_days": 90}},
    )

    fetched = client.get(f"/api/v1/backtests/{run_id}").json()["data"]["run"]
    snapshot = fetched["strategy_snapshot"]
    assert snapshot["parameters"]["tickers"] == ["AAA"]
    assert snapshot["parameters"]["lookback_days"] == 2
    assert fetched["inputs"]["strategy_snapshot"]["name"] == "Test Snapshot Strategy"


def test_parameter_sweep_persists_ranked_variant_runs():
    strategy = client.post(
        "/api/v1/paper-trading/strategies",
        json={
            "category": "short_term",
            "name": "Test Sweep Strategy",
            "description": "Sweep test.",
            "methodology": "Fixture strategy for parameter sweeps.",
            "parameters": {"tickers": ["AAA"], "risk": 3, "lookback_days": 2},
        },
    ).json()["data"]["strategy"]

    res = client.post(
        "/api/v1/backtests/sweep",
        json={
            "strategy_id": strategy["id"],
            "parameter": "risk",
            "values": [1, 3, 5],
            "start_date": "2020-01-01",
            "end_date": "2020-01-05",
            "starting_cash": 1000,
            "use_fixture_data": True,
        },
    )
    assert res.status_code == 200
    sweep = res.json()["data"]["sweep"]
    assert sweep["parameter"] == "risk"
    assert [row["rank"] for row in sweep["runs"]] == [1, 2, 3]
    assert sorted(row["value"] for row in sweep["runs"]) == [1, 3, 5]
    assert all("sharpe" in row["metrics"] and "turnover" in row["metrics"] for row in sweep["runs"])

    first_run = client.get(f"/api/v1/backtests/{sweep['runs'][0]['run_id']}").json()["data"]["run"]
    assert first_run["inputs"]["sweep"]["parameter"] == "risk"
    assert first_run["strategy_snapshot"]["parameters"]["risk"] == sweep["runs"][0]["value"]


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


def test_account_rebalance_preview_and_execute_reconcile_to_100():
    strat_a = client.post(
        "/api/v1/paper-trading/strategies",
        json={"category": "long_term", "name": "Lifecycle Trader A", "methodology": "x",
              "parameters": {"tickers": ["AAA"]}},
    ).json()["data"]["strategy"]
    strat_b = client.post(
        "/api/v1/paper-trading/strategies",
        json={"category": "short_term", "name": "Lifecycle Trader B", "methodology": "x",
              "parameters": {"tickers": ["BBB"]}},
    ).json()["data"]["strategy"]

    created = client.post(
        "/api/v1/paper-trading/accounts",
        json={"name": "Lifecycle Trader", "starting_cash": 10000,
              "allocations": [{"strategy_id": strat_a["id"], "weight": 60}]},
    ).json()["data"]["account"]
    assert created["invested_pct"] == 60
    assert created["cash_pct"] == 40
    assert created["reconciled_pct"] == 100

    preview = client.post(
        f"/api/v1/paper-trading/accounts/{created['id']}/rebalance-preview",
        json={"allocations": [
            {"strategy_id": strat_a["id"], "weight": 25},
            {"strategy_id": strat_b["id"], "weight": 50},
        ]},
    )
    assert preview.status_code == 200
    plan = preview.json()["data"]["preview"]
    assert plan["current_reconciled_pct"] == 100
    assert plan["target_reconciled_pct"] == 100
    assert plan["target_cash_pct"] == 25
    actions = {order["strategy_id"]: order for order in plan["orders"]}
    assert actions[strat_a["id"]]["action"] == "sell"
    assert actions[strat_a["id"]]["trade_dollars"] == -3500
    assert actions[strat_b["id"]]["action"] == "buy"
    assert actions[strat_b["id"]]["trade_dollars"] == 5000

    unchanged = client.get(f"/api/v1/paper-trading/accounts/{created['id']}").json()["data"]["account"]
    assert unchanged["allocations"][0]["strategy_id"] == strat_a["id"]
    assert unchanged["allocations"][0]["weight"] == 60

    executed = client.post(
        f"/api/v1/paper-trading/accounts/{created['id']}/rebalance",
        json={"allocations": [
            {"strategy_id": strat_a["id"], "weight": 25},
            {"strategy_id": strat_b["id"], "weight": 50},
        ]},
    )
    assert executed.status_code == 200
    account = executed.json()["data"]["account"]
    assert account["invested_pct"] == 75
    assert account["cash_pct"] == 25
    assert account["reconciled_pct"] == 100


def test_archived_strategy_remains_visible_in_account_context():
    strat = client.post(
        "/api/v1/paper-trading/strategies",
        json={"category": "long_term", "name": "Archive Context Strategy", "methodology": "x",
              "parameters": {"tickers": ["AAA"]}},
    ).json()["data"]["strategy"]
    account = client.post(
        "/api/v1/paper-trading/accounts",
        json={"name": "Archive Context Trader", "starting_cash": 5000,
              "allocations": [{"strategy_id": strat["id"], "weight": 80}]},
    ).json()["data"]["account"]

    deleted = client.delete(f"/api/v1/paper-trading/strategies/{strat['id']}")
    assert deleted.status_code == 200

    fetched = client.get(f"/api/v1/paper-trading/accounts/{account['id']}")
    assert fetched.status_code == 200
    alloc = fetched.json()["data"]["account"]["allocations"][0]
    assert alloc["name"] == "Archive Context Strategy"
    assert alloc["strategy_status"] == "archived"
    assert alloc["archived"] is True

    kept = client.put(
        f"/api/v1/paper-trading/accounts/{account['id']}",
        json={"bio": "keeps archived context", "allocations": [{"strategy_id": strat["id"], "weight": 80}]},
    )
    assert kept.status_code == 200
    assert kept.json()["data"]["account"]["allocations"][0]["archived"] is True


def test_account_performance_attribution_reconciles(monkeypatch):
    strat_a = client.post(
        "/api/v1/paper-trading/strategies",
        json={"category": "long_term", "name": "Attribution A", "methodology": "x",
              "parameters": {"tickers": ["AAA"]}},
    ).json()["data"]["strategy"]
    strat_b = client.post(
        "/api/v1/paper-trading/strategies",
        json={"category": "short_term", "name": "Attribution B", "methodology": "x",
              "parameters": {"tickers": ["BBB"]}},
    ).json()["data"]["strategy"]
    account = client.post(
        "/api/v1/paper-trading/accounts",
        json={"name": "Attribution Trader", "starting_cash": 10000,
              "allocations": [
                  {"strategy_id": strat_a["id"], "weight": 40},
                  {"strategy_id": strat_b["id"], "weight": 30},
              ]},
    ).json()["data"]["account"]

    def fake_backtest(*, strategy, start_date, end_date, starting_cash, **_):
        multiplier = 1.10 if strategy["name"] == "Attribution A" else 0.90
        ending = starting_cash * multiplier
        return {
            "equity_curve": [
                {"date": start_date, "equity": starting_cash, "benchmark_equity": starting_cash, "cash": 0},
                {"date": end_date, "equity": ending, "benchmark_equity": starting_cash, "cash": 0},
            ],
            "trades": [
                {"side": "buy", "value": starting_cash * 0.95},
                {"side": "sell", "value": ending, "pnl": ending - starting_cash},
            ],
            "warnings": [],
        }

    monkeypatch.setattr(account_service, "execute_backtest", fake_backtest)
    res = client.get(
        f"/api/v1/paper-trading/accounts/{account['id']}/performance?start=2020-01-01&end=2020-01-05"
    )
    assert res.status_code == 200
    perf = res.json()["data"]
    assert perf["risk"]["gross_exposure"] == 0.7
    assert perf["risk"]["cash_pct"] == 0.3
    assert perf["risk"]["concentration"] == 0.4
    assert perf["attribution"]["reconciliation"]["difference"] == 0
    assert perf["current_value"] == 10100
    assert perf["attribution"]["reconciliation"]["contribution_final"] + perf["cash_dollars"] == perf["current_value"]
    assert perf["contributions"][0]["name"] == "Attribution A"
    assert perf["contributions"][-1]["name"] == "Attribution B"
    assert perf["drawdown_curve"]
