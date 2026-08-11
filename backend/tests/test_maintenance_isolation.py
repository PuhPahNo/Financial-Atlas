import asyncio
import threading
import time
from contextlib import contextmanager

from app import main
from app.core import heavy_work
from app.jobs import maintenance_cycle


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


def test_maintenance_cycle_runs_both_phases_under_heavy_lock(monkeypatch):
    events = []

    @contextmanager
    def fake_lock():
        events.append("lock-enter")
        yield
        events.append("lock-exit")

    monkeypatch.setattr(maintenance_cycle, "heavy_work_lock", fake_lock)
    monkeypatch.setattr(maintenance_cycle, "prefer_child_for_oom_kill", lambda: events.append("oom"))
    monkeypatch.setattr(maintenance_cycle.warm_prices, "run", lambda: events.append("warm") or {"ok": 1})
    monkeypatch.setattr(
        maintenance_cycle.refresh_headlines,
        "run",
        lambda: events.append("refresh") or {"refreshed": 2, "failed": []},
    )

    result = maintenance_cycle.run("test")

    assert events == ["oom", "lock-enter", "warm", "refresh", "lock-exit"]
    assert result["warmed"] == {"ok": 1}
    assert result["refreshed"]["refreshed"] == 2


def test_parent_survives_killed_maintenance_child(monkeypatch):
    created = {}

    class FakeProcess:
        returncode = -9

        async def wait(self):
            return self.returncode

        def terminate(self):
            raise AssertionError("completed process should not be terminated")

        def kill(self):
            raise AssertionError("completed process should not be killed")

    async def create(*args, **kwargs):
        created["args"] = args
        created["env"] = kwargs["env"]
        return FakeProcess()

    monkeypatch.setattr(main.asyncio, "create_subprocess_exec", create)

    completed = asyncio.run(main._run_data_maintenance_process("nightly"))

    assert completed is False
    assert created["args"][-2:] == ("--reason", "nightly")
    assert created["env"]["MALLOC_ARENA_MAX"] == "2"
