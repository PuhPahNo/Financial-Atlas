from concurrent.futures import ThreadPoolExecutor
import threading
import time

import pytest

from app.core import cache


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(cache.settings, "cache_dir", tmp_path)
    monkeypatch.setattr(cache.settings, "cache_enabled", True)


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

