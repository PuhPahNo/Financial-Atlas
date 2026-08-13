"""Fail-safe for disposable workers inside a memory-limited service cgroup."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import threading
import time

MEMORY_GUARD_EXIT_CODE = 75
_MIB = 1024 * 1024
_DEFAULT_RESERVE_MB = 96
_DEFAULT_POLL_SECONDS = 0.05
_CGROUP_FILES = (
    (Path("/sys/fs/cgroup/memory.current"), Path("/sys/fs/cgroup/memory.max")),
    (
        Path("/sys/fs/cgroup/memory/memory.usage_in_bytes"),
        Path("/sys/fs/cgroup/memory/memory.limit_in_bytes"),
    ),
)


@dataclass(frozen=True)
class MemorySnapshot:
    current: int
    limit: int


def _cgroup_int(value: str, *, allow_zero: bool = False) -> int | None:
    if value.strip() == "max":
        return None
    try:
        parsed = int(value.strip())
    except ValueError:
        return None
    # cgroup v1 represents "unlimited" with a huge sentinel near 2**63.
    lower_bound = 0 if allow_zero else 1
    return parsed if lower_bound <= parsed < 1 << 60 else None


def cgroup_memory_snapshot() -> MemorySnapshot | None:
    """Return total container memory pressure for cgroup v2 or v1."""
    for current_path, limit_path in _CGROUP_FILES:
        try:
            current = _cgroup_int(
                current_path.read_text(encoding="ascii"), allow_zero=True,
            )
            limit = _cgroup_int(limit_path.read_text(encoding="ascii"))
        except OSError:
            continue
        if current is not None and limit is not None:
            return MemorySnapshot(current=current, limit=limit)
    return None


def pressure_threshold(limit: int, reserve_mb: int) -> int:
    """Keep configured headroom, but never reserve over half the cgroup."""
    reserve = min(max(16, reserve_mb) * _MIB, limit // 2)
    return limit - reserve


def under_pressure(snapshot: MemorySnapshot, reserve_mb: int) -> bool:
    return snapshot.current >= pressure_threshold(snapshot.limit, reserve_mb)


def arm_cgroup_memory_guard(label: str) -> bool:
    """Exit this disposable child before Render restarts the whole instance.

    The guard observes total cgroup usage, not only the child's RSS, because FastAPI,
    Next.js, and filesystem cache all share the same 512 MB service budget. It is a
    no-op outside a finite Linux cgroup. ``os._exit`` is intentional: at pressure the
    safest behavior is immediate child teardown; open database transactions roll back.
    """
    snapshot = cgroup_memory_snapshot()
    if snapshot is None:
        return False
    try:
        reserve_mb = int(os.environ.get("HEAVY_CHILD_MEMORY_RESERVE_MB", _DEFAULT_RESERVE_MB))
        poll_seconds = float(os.environ.get("HEAVY_CHILD_MEMORY_POLL_SECONDS", _DEFAULT_POLL_SECONDS))
    except ValueError:
        reserve_mb, poll_seconds = _DEFAULT_RESERVE_MB, _DEFAULT_POLL_SECONDS

    def stop(latest: MemorySnapshot) -> None:
        message = (
            f"memory guard stopped {label}: current_mb={latest.current / _MIB:.1f} "
            f"limit_mb={latest.limit / _MIB:.1f} reserve_mb={reserve_mb}\n"
        )
        try:
            os.write(2, message.encode("utf-8", errors="replace"))
        finally:
            os._exit(MEMORY_GUARD_EXIT_CODE)

    if under_pressure(snapshot, reserve_mb):
        stop(snapshot)

    def watch() -> None:
        while True:
            latest = cgroup_memory_snapshot()
            if latest is not None and under_pressure(latest, reserve_mb):
                stop(latest)
            time.sleep(max(0.02, poll_seconds))

    threading.Thread(target=watch, name="atlas-memory-guard", daemon=True).start()
    return True
