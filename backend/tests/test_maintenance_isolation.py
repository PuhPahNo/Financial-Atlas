import asyncio
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta

from app import main
from app.core import heavy_work
from app.db import session_scope
from app.jobs import maintenance_cycle, refresh_headlines
from app.models.paper_trading import BacktestEquityPoint, BacktestRun, BacktestTrade, TradingStrategy


def test_heavy_work_lock_is_reentrant_and_serializes_threads(tmp_path, monkeypatch):
    monkeypatch.setattr(heavy_work, "_LOCK_PATH", tmp_path / "heavy.lock")
    entered = []
    first_inside = threading.Event()
    release_first = threading.Event()

    def first():
        with heavy_work.lock():
            with heavy_work.lock():
                entered.append("first")
                first_inside.set()
                release_first.wait(timeout=2)

    def second():
        first_inside.wait(timeout=2)
        with heavy_work.lock():
            entered.append("second")

    t1 = threading.Thread(target=first)
    t2 = threading.Thread(target=second)
    t1.start()
    t2.start()
    first_inside.wait(timeout=2)
    time.sleep(0.02)
    assert entered == ["first"]
    release_first.set()
    t1.join(timeout=2)
    t2.join(timeout=2)
    assert entered == ["first", "second"]


def test_maintenance_cycle_runs_one_headline_under_heavy_lock(monkeypatch):
    events = []

    @contextmanager
    def fake_lock():
        events.append("lock-enter")
        yield
        events.append("lock-exit")

    monkeypatch.setattr(maintenance_cycle, "heavy_work_lock", fake_lock)
    monkeypatch.setattr(maintenance_cycle, "prefer_child_for_oom_kill", lambda: events.append("oom"))
    monkeypatch.setattr(maintenance_cycle, "arm_cgroup_memory_guard", lambda label: events.append(("guard", label)))
    monkeypatch.setattr(
        maintenance_cycle,
        "_run_headline",
        lambda strategy_id, **_kwargs: events.append(("headline", strategy_id)) or {"strategy_id": strategy_id},
    )

    result = maintenance_cycle.run("test", "headline", strategy_id=42)

    assert events == [
        "oom",
        ("guard", "maintenance test/headline"),
        "lock-enter",
        ("headline", 42),
        "lock-exit",
    ]
    assert result["refreshed"] == {"strategy_id": 42}


def test_refresh_headline_runs_exactly_one_strategy_without_pruning(monkeypatch):
    calls = []
    monkeypatch.setattr(refresh_headlines, "init_db", lambda: calls.append("init"))
    monkeypatch.setattr(
        refresh_headlines.service,
        "get_strategy",
        lambda strategy_id: {"strategy": {"id": strategy_id, "name": "Quality Low Vol"}},
    )
    monkeypatch.setattr(
        refresh_headlines.service,
        "run_backtest",
        lambda payload, **kwargs: calls.append(
            ("backtest", payload.strategy_id, payload.persist_headline, kwargs)
        ),
    )
    monkeypatch.setattr(
        refresh_headlines,
        "prune_runs",
        lambda: (_ for _ in ()).throw(AssertionError("per-strategy child must not prune")),
    )

    result = refresh_headlines.run_one(42)

    assert calls == ["init", ("backtest", 42, True, {"return_detail": False})]
    assert result["strategy_id"] == 42
    assert result["strategy"] == "Quality Low Vol"


def test_parent_runs_each_headline_in_a_fresh_child_and_continues_after_kill(monkeypatch):
    created = []
    returncodes = iter([0, 0, -9, 0, 0])

    class FakeProcess:
        def __init__(self, returncode):
            self.returncode = returncode

        async def wait(self):
            return self.returncode

        def terminate(self):
            raise AssertionError("completed process should not be terminated")

        def kill(self):
            raise AssertionError("completed process should not be killed")

    async def create(*args, **kwargs):
        created.append({"args": args, "env": kwargs["env"]})
        return FakeProcess(next(returncodes))

    monkeypatch.setattr(main.asyncio, "create_subprocess_exec", create)
    monkeypatch.setattr(
        main,
        "_headline_refresh_targets",
        lambda: [(11, "First"), (22, "Second"), (33, "Third")],
    )

    completed = asyncio.run(main._run_data_maintenance_process("nightly"))

    assert completed is False
    commands = [entry["args"] for entry in created]
    assert [command[command.index("--phase") + 1] for command in commands] == [
        "warm", "headline", "headline", "headline", "prune",
    ]
    assert [command[command.index("--strategy-id") + 1] for command in commands[1:4]] == [
        "11", "22", "33",
    ]
    assert all(entry["env"]["MALLOC_ARENA_MAX"] == "2" for entry in created)


def test_retention_prune_deletes_in_bounded_batches():
    old = datetime.now() - timedelta(days=10)
    with session_scope() as session:
        strategy = TradingStrategy(
            category="long_term",
            name="Test Retention Strategy",
            slug="test-retention-strategy",
            origin="user",
            status="active",
        )
        session.add(strategy)
        session.flush()
        strategy_id = strategy.id
        session.add_all([
            BacktestRun(
                strategy_id=strategy_id,
                name=f"Test Retention {index}",
                start_date=old.date(),
                end_date=old.date() + timedelta(days=1),
                starting_cash=1000,
                status="completed",
                created_at=old + timedelta(seconds=index),
            )
            for index in range(510)
        ])

    deleted = refresh_headlines.prune_runs(keep_per_strategy=2, keep_days=5)

    with session_scope() as session:
        remaining = session.query(BacktestRun).filter_by(strategy_id=strategy_id).all()
        retention_rows = [run for run in remaining if (run.name or "").startswith("Test Retention")]
        assert len(retention_rows) <= 2
        assert deleted >= 508
        remaining_ids = [run.id for run in retention_rows]
        session.query(BacktestTrade).filter(BacktestTrade.run_id.in_(remaining_ids)).delete(
            synchronize_session=False,
        )
        session.query(BacktestEquityPoint).filter(BacktestEquityPoint.run_id.in_(remaining_ids)).delete(
            synchronize_session=False,
        )
        session.query(BacktestRun).filter(BacktestRun.id.in_(remaining_ids)).delete(synchronize_session=False)
        session.query(TradingStrategy).filter_by(id=strategy_id).delete(synchronize_session=False)
