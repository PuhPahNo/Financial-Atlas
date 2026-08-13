from pathlib import Path
import subprocess
import sys

from app.jobs import isolated_backtests, memory_guard


def test_cgroup_v2_snapshot_and_pressure_threshold(tmp_path, monkeypatch):
    current, limit = tmp_path / "memory.current", tmp_path / "memory.max"
    current.write_text(str(430 * 1024 * 1024), encoding="ascii")
    limit.write_text(str(512 * 1024 * 1024), encoding="ascii")
    monkeypatch.setattr(memory_guard, "_CGROUP_FILES", ((current, limit),))

    snapshot = memory_guard.cgroup_memory_snapshot()

    assert snapshot == memory_guard.MemorySnapshot(430 * 1024 * 1024, 512 * 1024 * 1024)
    assert memory_guard.under_pressure(snapshot, reserve_mb=96) is True
    assert memory_guard.under_pressure(snapshot, reserve_mb=64) is False


def test_unlimited_cgroup_is_not_armed(tmp_path, monkeypatch):
    current, limit = tmp_path / "memory.current", tmp_path / "memory.max"
    current.write_text("123", encoding="ascii")
    limit.write_text("max", encoding="ascii")
    monkeypatch.setattr(memory_guard, "_CGROUP_FILES", ((current, limit),))

    assert memory_guard.cgroup_memory_snapshot() is None
    assert memory_guard.arm_cgroup_memory_guard("test") is False


def test_guard_exits_only_the_disposable_child(tmp_path):
    current, limit = tmp_path / "memory.current", tmp_path / "memory.max"
    current.write_text(str(430 * 1024 * 1024), encoding="ascii")
    limit.write_text(str(512 * 1024 * 1024), encoding="ascii")
    backend_dir = Path(__file__).resolve().parents[1]
    script = """
import sys
import time
from pathlib import Path
from app.jobs import memory_guard

memory_guard._CGROUP_FILES = ((Path(sys.argv[1]), Path(sys.argv[2])),)
memory_guard.arm_cgroup_memory_guard("test child")
time.sleep(2)
"""

    completed = subprocess.run(
        [sys.executable, "-c", script, str(current), str(limit)],
        cwd=backend_dir,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == memory_guard.MEMORY_GUARD_EXIT_CODE
    assert "memory guard stopped test child" in completed.stderr


def test_guard_stops_child_when_cgroup_pressure_rises(tmp_path):
    current, limit = tmp_path / "memory.current", tmp_path / "memory.max"
    current.write_text(str(300 * 1024 * 1024), encoding="ascii")
    limit.write_text(str(512 * 1024 * 1024), encoding="ascii")
    backend_dir = Path(__file__).resolve().parents[1]
    script = """
import sys
import time
from pathlib import Path
from app.jobs import memory_guard

memory_guard._CGROUP_FILES = ((Path(sys.argv[1]), Path(sys.argv[2])),)
memory_guard.arm_cgroup_memory_guard("rising child")
print("armed", flush=True)
time.sleep(5)
"""
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(current), str(limit)],
        cwd=backend_dir,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert process.stdout is not None
    assert process.stdout.readline().strip() == "armed"
    current.write_text(str(430 * 1024 * 1024), encoding="ascii")
    _stdout, stderr = process.communicate(timeout=3)

    assert process.returncode == memory_guard.MEMORY_GUARD_EXIT_CODE
    assert "memory guard stopped rising child" in stderr


def test_memory_guard_exit_has_actionable_parent_error():
    assert isolated_backtests.process_failure(memory_guard.MEMORY_GUARD_EXIT_CODE) == (
        "Backtest worker stopped before the service memory limit"
    )
