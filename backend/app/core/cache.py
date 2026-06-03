"""Filesystem response cache with TTL (PRD 05 §4).

Keyed by ``{namespace}:{key}``; stored as JSON on disk. On a hit within TTL the
cached payload is returned; expired entries are recomputed. A ``get_or_set``
helper provides single-flight-ish behaviour for the common fetch path. If the
loader fails and a stale entry exists, the stale value is returned flagged so
callers can surface ``meta.stale`` (PRD 04 §5).
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .config import settings

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


def _path_for(namespace: str, key: str) -> Path:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
    return settings.cache_dir / namespace / f"{digest}.json"


def _read(path: Path) -> dict | None:
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Unique temp file per write so concurrent writers to the same key don't
    # collide on a shared .tmp (which caused FileNotFoundError on os.replace).
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


def get_or_set(namespace: str, key: str, ttl_seconds: int, loader: Callable[[], Any]) -> CacheResult:
    """Return cached value if fresh, else call ``loader`` and cache it.

    On loader failure, fall back to a stale cached value when available.
    """
    path = _path_for(namespace, key)
    now = time.time()
    record = _read(path) if settings.cache_enabled else None
    if record is not None and now - record.get("stored_at", 0) <= ttl_seconds:
        return CacheResult(value=record["value"], stale=False, age_seconds=now - record.get("stored_at", 0))

    # Single-flight: only one thread loads a given key; others wait then re-read.
    with _lock_for(f"{namespace}:{key}"):
        now = time.time()
        record = _read(path) if settings.cache_enabled else None
        if record is not None and now - record.get("stored_at", 0) <= ttl_seconds:
            return CacheResult(value=record["value"], stale=False, age_seconds=now - record.get("stored_at", 0))

        try:
            value = loader()
        except Exception:
            if record is not None:  # serve stale rather than fail (PRD 02 §9)
                return CacheResult(value=record["value"], stale=True, age_seconds=now - record.get("stored_at", 0))
            raise

        if settings.cache_enabled:
            _write(path, {"stored_at": now, "value": value})
        return CacheResult(value=value, stale=False, age_seconds=0.0)
