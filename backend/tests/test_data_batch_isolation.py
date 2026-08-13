"""Resource-boundary regressions for screener and snapshot batches."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from app.jobs import data_batch_child, isolated_data
from app.services import screener


def test_data_batch_child_arms_guard_before_locked_work(monkeypatch):
    events = []

    class Lock:
        def __enter__(self):
            events.append("lock-enter")

        def __exit__(self, *_args):
            events.append("lock-exit")

    monkeypatch.setattr(data_batch_child, "prefer_child_for_oom_kill", lambda: events.append("oom"))
    monkeypatch.setattr(
        data_batch_child,
        "arm_cgroup_memory_guard",
        lambda label: events.append(("guard", label)),
    )
    monkeypatch.setattr(data_batch_child, "heavy_work_lock", Lock)
    monkeypatch.setattr(
        screener,
        "warm_universe",
        lambda **kwargs: events.append(("warm", kwargs)) or {"warmed": 1},
    )

    result = data_batch_child.execute(
        "screener-warm", {"tickers": ["AAA"], "include_default": False},
    )

    assert result == {"warmed": 1}
    assert events == [
        "oom",
        ("guard", "data batch screener-warm"),
        "lock-enter",
        ("warm", {"tickers": ["AAA"], "include_default": False}),
        "lock-exit",
    ]


def test_parent_screener_batch_uses_disposable_child(monkeypatch):
    launched = []

    def run(args, **kwargs):
        launched.append((args, kwargs))
        output = Path(args[args.index("--output-json") + 1])
        output.write_text(json.dumps({"attempted": 2, "ingested": ["AAA", "BBB"]}), encoding="utf-8")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(isolated_data.subprocess, "run", run)

    result = isolated_data.ingest(["AAA", "BBB"])

    args, kwargs = launched[0]
    assert args[1:3] == ["-m", "app.jobs.data_batch_child"]
    assert args[args.index("--operation") + 1] == "screener-ingest"
    assert kwargs["env"]["MALLOC_ARENA_MAX"] == "2"
    assert result["ingested"] == ["AAA", "BBB"]
