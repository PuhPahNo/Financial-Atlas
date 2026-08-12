"""Process-boundary regressions for memory-heavy backtest entry points."""
from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from app import main
from app.core.errors import ProviderError
from app.jobs import isolated_backtests
from app.paper_trading import service
from app.paper_trading.schemas import BacktestRequest, ParameterSweepRequest, StrategyCreate


def _request() -> BacktestRequest:
    return BacktestRequest(
        strategy_id=7,
        start_date=date(2023, 1, 1),
        end_date=date(2024, 1, 1),
    )


def test_queued_worker_uses_disposable_child_and_marks_oom(monkeypatch):
    created = []
    failed = []

    class FakeProcess:
        async def wait(self):
            return -9

        def terminate(self):
            raise AssertionError("completed process should not be terminated")

        def kill(self):
            raise AssertionError("completed process should not be killed")

    async def create(*args, **kwargs):
        created.append((args, kwargs))
        return FakeProcess()

    monkeypatch.setattr(main.asyncio, "create_subprocess_exec", create)
    monkeypatch.setattr(main.pt_service, "fail_backtest", lambda run_id, message: failed.append((run_id, message)))

    completed = asyncio.run(main._run_backtest_child(42))

    assert completed is False
    args, kwargs = created[0]
    assert args[1:3] == ("-m", "app.jobs.backtest_child")
    assert args[-2:] == ("--run-id", "42")
    assert kwargs["env"]["MALLOC_ARENA_MAX"] == "2"
    assert failed == [(42, "Backtest worker was terminated by SIGKILL")]


def test_synchronous_backtest_uses_child_and_surfaces_child_failure(monkeypatch):
    failed = []
    monkeypatch.setattr(
        isolated_backtests.service,
        "start_backtest",
        lambda payload: {"run": {"id": 19, "status": "running"}},
    )
    monkeypatch.setattr(isolated_backtests, "_run_child_sync", lambda run_id: -9)
    monkeypatch.setattr(
        isolated_backtests.service,
        "fail_backtest",
        lambda run_id, message: failed.append((run_id, message)),
    )

    with pytest.raises(ProviderError, match="terminated by SIGKILL"):
        isolated_backtests.run_backtest(_request())

    assert failed == [(19, "Backtest worker was terminated by SIGKILL")]


def test_synchronous_backtest_marks_process_launch_failure(monkeypatch):
    failed = []
    monkeypatch.setattr(
        isolated_backtests.service,
        "start_backtest",
        lambda payload: {"run": {"id": 23, "status": "running"}},
    )
    monkeypatch.setattr(
        isolated_backtests,
        "_run_child_sync",
        lambda run_id: (_ for _ in ()).throw(OSError("no process slots")),
    )
    monkeypatch.setattr(
        isolated_backtests.service,
        "fail_backtest",
        lambda run_id, message: failed.append((run_id, message)),
    )

    with pytest.raises(ProviderError, match="could not start"):
        isolated_backtests.run_backtest(_request())

    assert failed == [(23, "Backtest worker could not start: no process slots")]


def test_parameter_sweep_launches_fresh_child_per_value(monkeypatch):
    payload = ParameterSweepRequest(
        strategy_id=7,
        parameter="risk",
        values=[1, 3, 5],
        start_date=date(2023, 1, 1),
        end_date=date(2024, 1, 1),
    )
    launched = []

    monkeypatch.setattr(
        isolated_backtests.service,
        "prepare_parameter_sweep",
        lambda request: ("Quality", [{"value": value, "variant": {"parameters": {"risk": value}}}
                                     for value in request.values]),
    )
    monkeypatch.setattr(
        isolated_backtests.service,
        "start_sweep_backtest",
        lambda request, item: {"run": {"id": int(item["value"]), "status": "running"}},
    )
    monkeypatch.setattr(
        isolated_backtests,
        "_run_child_sync",
        lambda run_id: launched.append(run_id) or 0,
    )
    monkeypatch.setattr(
        isolated_backtests.service,
        "get_backtest",
        lambda run_id: {
            "run": {
                "id": run_id,
                "status": "completed",
                "metrics": {"total_return": run_id / 100},
                "warnings": [],
                "strategy_snapshot": {"parameters": {"risk": run_id}},
            }
        },
    )

    result = isolated_backtests.run_parameter_sweep(payload)

    assert launched == [1, 3, 5]
    assert [row["value"] for row in result["sweep"]["runs"]] == [5, 3, 1]
    assert [row["rank"] for row in result["sweep"]["runs"]] == [1, 2, 3]


def test_manual_headline_refresh_uses_one_child_per_strategy(monkeypatch):
    launched = []
    monkeypatch.setattr(
        isolated_backtests.service,
        "list_strategies",
        lambda: {"strategies": [{"id": 11, "name": "First"}, {"id": 22, "name": "Second"}]},
    )
    monkeypatch.setattr(
        isolated_backtests,
        "_run_maintenance_child_sync",
        lambda phase, **kwargs: launched.append((phase, kwargs)) or SimpleNamespace(returncode=0, result={}),
    )

    result = isolated_backtests.refresh_headlines(years=4)

    assert [phase for phase, _ in launched] == ["headline", "headline", "prune"]
    assert [kwargs.get("strategy_id") for _, kwargs in launched[:2]] == [11, 22]
    assert all(kwargs["years"] == 4 for _, kwargs in launched[:2])
    assert result["refreshed"] == 2


def test_account_sleeve_result_crosses_process_boundary(monkeypatch):
    launched = []

    def run(args, **_kwargs):
        launched.append(args)
        output = args[args.index("--output-json") + 1]
        Path(output).write_text(
            '{"equity_curve": [], "trades": [], "warnings": [], "residual_cash": 1000, "final_holdings": []}',
            encoding="utf-8",
        )
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(isolated_backtests.subprocess, "run", run)

    result = isolated_backtests.run_account_sleeve(
        {"name": "Quality", "category": "long_term", "parameters": {"tickers": ["SPY"]}},
        ["SPY"],
        date(2023, 1, 1),
        date(2024, 1, 1),
        1000,
    )

    assert result["residual_cash"] == 1000
    assert launched[0][1:3] == ["-m", "app.jobs.backtest_child"]
    assert "--input-json" in launched[0]


def test_real_child_reads_shared_job_and_persists_failure():
    """Integration proof: an exec'd interpreter sees the same DB and settles state."""
    payload = BacktestRequest(
        strategy=StrategyCreate(
            category="long_term",
            name="Test Isolated Invalid Window",
            parameters={"tickers": ["SPY"]},
        ),
        start_date=date(2024, 1, 2),
        end_date=date(2024, 1, 1),
    )
    run_id = service.start_backtest(payload)["run"]["id"]

    assert isolated_backtests._run_child_sync(run_id) == 1
    failed = service.get_backtest(run_id)["run"]
    assert failed["status"] == "failed"
    assert "end_date must be after start_date" in failed["warnings"][0]
