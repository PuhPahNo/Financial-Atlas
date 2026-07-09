"""Filesystem response cache with TTL (PRD 05 §4).

Keyed by ``{namespace}:{key}``; stored as JSON on disk. On a hit within TTL the
cached payload is returned; expired entries are recomputed. A ``get_or_set``
helper provides single-flight-ish behaviour for the common fetch path. If the
loader fails and a stale entry exists, the stale value is returned flagged so
callers can surface ``meta.stale`` (PRD 04 §5).
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import hashlib
import json
import logging
import os
import shutil
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .config import settings

logger = logging.getLogger(__name__)

# Per-key locks for single-flight: only one thread fetches a given key at a time;
# concurrent callers wait and then read the freshly-written value.
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock_for(token: str) -> threading.Lock:
    with _locks_guard:
        lock = _locks.get(token)
        if lock is None:
            lock = threading.Lock()
            _locks[token] = lock
        return lock


@dataclass
class CacheResult:
    value: Any
    stale: bool = False
    age_seconds: float | None = None
    stored_at: float | None = None
    status: str = "miss"


@dataclass(frozen=True)
class CacheEvent:
    namespace: str
    key_hash: str
    status: str
    stale: bool
    age_seconds: float | None
    stored_at: float | None


_trace: ContextVar[list[CacheEvent] | None] = ContextVar("cache_trace", default=None)


@contextmanager
def trace_events():
    """Collect cache accesses made inside the context.

    This avoids pushing cache metadata through every provider method signature while still allowing
    composed API responses to summarize cache behavior per section.
    """
    events: list[CacheEvent] = []
    token = _trace.set(events)
    try:
        yield events
    finally:
        _trace.reset(token)


def _emit(namespace: str, key: str, result: CacheResult) -> None:
    events = _trace.get()
    if events is None:
        return
    events.append(CacheEvent(
        namespace=namespace,
        key_hash=hashlib.sha256(key.encode("utf-8")).hexdigest()[:12],
        status=result.status,
        stale=result.stale,
        age_seconds=result.age_seconds,
        stored_at=result.stored_at,
    ))


def _path_for(namespace: str, key: str) -> Path:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
    return settings.cache_dir / namespace / f"{digest}.json"


def _read(path: Path) -> dict | None:
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        # Missing file, unreadable mount, or corrupt JSON — treat as a cache miss.
        # (FileNotFoundError is an OSError subclass.)
        return None


_write_count = 0


def _maybe_prune(*, force: bool = False) -> int:
    """Prune old cache entries before they can crowd out durable data.

    The first write in each process checks the disk, followed by every 200th write.
    ``force`` is used after a failed write so a full persistent disk gets one chance
    to recover. The size cap and the shared-disk free-space reserve are independent:
    ``cache_max_mb=0`` disables only the cache-size cap.
    """
    global _write_count
    _write_count += 1
    if not force and _write_count != 1 and _write_count % 200 != 0:
        return 0

    cap_mb = max(0, getattr(settings, "cache_max_mb", 0) or 0)
    min_free_mb = max(0, getattr(settings, "cache_min_free_mb", 0) or 0)
    if cap_mb <= 0 and min_free_mb <= 0:
        return 0

    root = settings.cache_dir
    try:
        entries: list[tuple[float, int, Path]] = []
        total = 0
        for p in root.rglob("*.json"):
            try:
                st = p.stat()
            except OSError:
                continue
            entries.append((st.st_mtime, st.st_size, p))
            total += st.st_size

        target = total
        if cap_mb > 0:
            limit = cap_mb * 1024 * 1024
            if total > limit:
                target = min(target, int(limit * 0.9))

        if min_free_mb > 0:
            free = shutil.disk_usage(root).free
            reserve = min_free_mb * 1024 * 1024
            if free < reserve:
                target = min(target, max(0, total - (reserve - free)))

        if target >= total:
            return 0

        entries.sort()  # oldest first
        removed = 0
        for _mtime, size, p in entries:
            if total <= target:
                break
            try:
                p.unlink()
                total -= size
                removed += 1
            except OSError:
                pass
        if removed:
            logger.info("pruned %d cache files to preserve disk headroom", removed)
        return removed
    except Exception:  # noqa: BLE001 — pruning is best-effort, never break a write
        return 0


def _write_atomic(path: Path, payload: dict) -> None:
    """Write one cache record atomically."""
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _maybe_prune()
    try:
        _write_atomic(path, payload)
    except OSError:
        # A process can start against an already-full persistent disk. Prune
        # immediately and retry once; permission/read-only errors still bubble
        # up to the existing best-effort cache fallback.
        if not _maybe_prune(force=True):
            raise
        _write_atomic(path, payload)


def peek(namespace: str, key: str, ttl_seconds: int) -> Any | None:
    """Return a cached value if present and fresh, else None — without invoking a loader.
    Used for lightweight flags (e.g. a dead-ticker skiplist)."""
    if not settings.cache_enabled:
        return None
    record = _read(_path_for(namespace, key))
    if record is not None and time.time() - record.get("stored_at", 0) <= ttl_seconds:
        return record["value"]
    return None


def put(namespace: str, key: str, value: Any) -> None:
    """Write a value to the cache directly (no loader). Counterpart to ``peek``."""
    if settings.cache_enabled:
        try:
            _write(_path_for(namespace, key), {"stored_at": time.time(), "value": value})
        except OSError as exc:  # full/read-only disk — caching is best-effort, never fatal
            logger.warning("cache put failed (%s): %s", type(exc).__name__, namespace)


def _fresh_hit(record: dict, now: float) -> CacheResult:
    stored_at = record.get("stored_at")
    return CacheResult(
        value=record["value"],
        stale=False,
        age_seconds=now - stored_at,
        stored_at=stored_at,
        status="hit",
    )


def _read_cached(
    path: Path,
    namespace: str,
    key: str,
    ttl_seconds: int,
) -> tuple[CacheResult | None, dict | None, float]:
    now = time.time()
    record = _read(path) if settings.cache_enabled else None
    if record is not None and now - record.get("stored_at", 0) <= ttl_seconds:
        result = _fresh_hit(record, now)
        _emit(namespace, key, result)
        return result, record, now
    return None, record, now


def get_or_set(namespace: str, key: str, ttl_seconds: int, loader: Callable[[], Any]) -> CacheResult:
    """Return cached value if fresh, else call ``loader`` and cache it.

    On loader failure, fall back to a stale cached value when available.
    """
    path = _path_for(namespace, key)
    result, _record, _now = _read_cached(path, namespace, key, ttl_seconds)
    if result is not None:
        return result

    # Single-flight: only one thread loads a given key; others wait then re-read.
    with _lock_for(f"{namespace}:{key}"):
        result, record, now = _read_cached(path, namespace, key, ttl_seconds)
        if result is not None:
            return result

        try:
            value = loader()
        except Exception:
            if record is not None:  # serve stale rather than fail (PRD 02 §9)
                result = CacheResult(
                    value=record["value"],
                    stale=True,
                    age_seconds=now - record.get("stored_at", 0),
                    stored_at=record.get("stored_at"),
                    status="stale",
                )
                _emit(namespace, key, result)
                return result
            raise

        persisted = False
        if settings.cache_enabled:
            try:
                _write(path, {"stored_at": now, "value": value})
                persisted = True
            except OSError as exc:
                # Disk full or read-only: we already have the freshly-loaded value,
                # so return it uncached rather than failing the whole request. The
                # cache is an optimization, not a source of truth.
                logger.warning(
                    "cache write failed (%s); serving '%s' uncached", type(exc).__name__, namespace
                )
        result = CacheResult(
            value=value,
            stale=False,
            age_seconds=0.0 if persisted else None,
            stored_at=now if persisted else None,
            status="miss" if persisted else "bypass",
        )
        _emit(namespace, key, result)
        return result
