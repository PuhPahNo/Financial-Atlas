from concurrent.futures import ThreadPoolExecutor
import os
import shutil
import threading
import time

import pytest

from app.core import cache


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(cache.settings, "cache_dir", tmp_path)
    monkeypatch.setattr(cache.settings, "cache_enabled", True)
    monkeypatch.setattr(cache.settings, "cache_max_mb", 512)
    monkeypatch.setattr(cache.settings, "cache_min_free_mb", 0)
    monkeypatch.setattr(cache, "_write_count", 0)


def test_get_or_set_records_miss_then_hit_with_trace():
    calls = 0

    def loader():
        nonlocal calls
        calls += 1
        return {"value": 42}

    with cache.trace_events() as first_events:
        first = cache.get_or_set("unit", "trace-hit", ttl_seconds=60, loader=loader)
    with cache.trace_events() as second_events:
        second = cache.get_or_set("unit", "trace-hit", ttl_seconds=60, loader=loader)

    assert first.value == {"value": 42}
    assert first.status == "miss"
    assert second.value == {"value": 42}
    assert second.status == "hit"
    assert second.stored_at is not None
    assert calls == 1
    assert [event.status for event in first_events] == ["miss"]
    assert [event.status for event in second_events] == ["hit"]


def test_get_or_set_serves_stale_cache_when_refresh_fails():
    cache.get_or_set("unit", "stale-fallback", ttl_seconds=60, loader=lambda: {"value": "old"})

    def failing_loader():
        raise RuntimeError("upstream unavailable")

    with cache.trace_events() as events:
        result = cache.get_or_set("unit", "stale-fallback", ttl_seconds=-1, loader=failing_loader)

    assert result.value == {"value": "old"}
    assert result.stale is True
    assert result.status == "stale"
    assert events[0].stale is True
    assert events[0].status == "stale"


def test_get_or_set_serves_uncached_when_disk_write_fails(monkeypatch):
    # A full/read-only disk (OSError on write) must not sink the request: we already
    # have the loaded value, so return it uncached rather than propagating the error.
    def boom(*_a, **_k):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(cache, "_write", boom)

    with cache.trace_events() as events:
        result = cache.get_or_set("unit", "disk-full", ttl_seconds=60, loader=lambda: {"value": "live"})

    assert result.value == {"value": "live"}
    assert result.status == "bypass"  # not persisted
    assert result.stored_at is None
    assert events[0].status == "bypass"


def test_put_swallows_disk_write_error(monkeypatch):
    monkeypatch.setattr(cache, "_write", lambda *a, **k: (_ for _ in ()).throw(OSError("read-only")))
    cache.put("unit", "skiplist", {"dead": True})  # must not raise


def test_first_write_prunes_cache_over_size_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(cache.settings, "cache_max_mb", 1)
    oldest = tmp_path / "unit" / "oldest.json"
    newest = tmp_path / "unit" / "newest.json"
    oldest.parent.mkdir(parents=True)
    oldest.write_bytes(b"x" * 700_000)
    newest.write_bytes(b"x" * 700_000)
    os.utime(oldest, (1, 1))
    os.utime(newest, (2, 2))

    cache.put("unit", "fresh", {"value": 1})

    assert not oldest.exists()
    assert newest.exists()
    assert cache.peek("unit", "fresh", ttl_seconds=60) == {"value": 1}


def test_prune_preserves_shared_disk_free_space(tmp_path, monkeypatch):
    monkeypatch.setattr(cache.settings, "cache_max_mb", 0)
    monkeypatch.setattr(cache.settings, "cache_min_free_mb", 1)
    entry = tmp_path / "unit" / "large.json"
    entry.parent.mkdir(parents=True)
    entry.write_bytes(b"x" * 1_200_000)
    monkeypatch.setattr(shutil, "disk_usage", lambda _path: shutil._ntuple_diskusage(10_000_000, 10_000_000, 0))

    cache.put("unit", "fresh", {"value": 1})

    assert not entry.exists()
    assert cache.peek("unit", "fresh", ttl_seconds=60) == {"value": 1}


def test_write_prunes_and_retries_once_after_oserror(monkeypatch):
    attempts = 0

    def flaky_write(path, payload):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError(28, "No space left on device")
        path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(cache, "_write_atomic", flaky_write)
    monkeypatch.setattr(cache, "_maybe_prune", lambda *, force=False: 1 if force else 0)

    cache.put("unit", "retry", {"value": 1})

    assert attempts == 2


def test_get_or_set_single_flight_deduplicates_concurrent_loaders():
    calls = 0
    lock = threading.Lock()

    def loader():
        nonlocal calls
        with lock:
            calls += 1
        time.sleep(0.05)
        return {"value": "shared"}

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [
            pool.submit(cache.get_or_set, "unit", "single-flight", 60, loader)
            for _ in range(8)
        ]
        results = [future.result() for future in futures]

    assert calls == 1
    assert {result.value["value"] for result in results} == {"shared"}
    assert sum(result.status == "miss" for result in results) == 1
    assert sum(result.status == "hit" for result in results) == 7
