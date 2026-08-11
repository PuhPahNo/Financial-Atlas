"""Cross-process serialization for memory-heavy work on the single small instance."""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
from pathlib import Path
import threading

_LOCK_PATH = Path("/tmp/financial-atlas-heavy-work.lock")
_PROCESS_LOCK = threading.RLock()
_THREAD_STATE = threading.local()


@contextmanager
def lock():
    """Allow one heavy workload across the web and maintenance processes.

    The thread-local depth makes nested active backtests inside a maintenance phase
    reentrant. The process-local RLock handles threads; ``flock`` handles the sibling
    maintenance process launched by the web service.
    """
    with _PROCESS_LOCK:
        depth = getattr(_THREAD_STATE, "depth", 0)
        if depth:
            _THREAD_STATE.depth = depth + 1
            try:
                yield
            finally:
                _THREAD_STATE.depth -= 1
            return

        _LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _LOCK_PATH.open("a+", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            _THREAD_STATE.depth = 1
            try:
                yield
            finally:
                _THREAD_STATE.depth = 0
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
