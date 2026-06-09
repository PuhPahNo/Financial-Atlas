"""In-memory fixed-window rate limiting for abuse-prone local workflows."""
from __future__ import annotations

import threading
import time

from fastapi import Request

from .config import settings
from .errors import RateLimitError

_lock = threading.Lock()
_buckets: dict[str, tuple[int, int]] = {}


def _client_key(request: Request, group: str) -> str:
    # Use the *last* X-Forwarded-For hop: it's the one appended by our own proxy, so a
    # client can't diversify buckets by spoofing the header. Never key on anything the
    # client fully controls (e.g. the session cookie) — that made the limit bypassable
    # by rotating fake values.
    forwarded = request.headers.get("x-forwarded-for", "")
    ip = forwarded.rsplit(",", 1)[-1].strip() if forwarded else ""
    if not ip and request.client:
        ip = request.client.host
    return f"{group}:{ip or 'unknown'}"


def check_rate_limit(request: Request, *, group: str, limit: int, window_seconds: int = 60) -> None:
    if limit <= 0:
        return
    now = int(time.time())
    window = now // window_seconds
    key = _client_key(request, group)
    with _lock:
        current_window, count = _buckets.get(key, (window, 0))
        if current_window != window:
            current_window, count = window, 0
        count += 1
        _buckets[key] = (current_window, count)
        if count > limit:
            retry_after = ((window + 1) * window_seconds) - now
            raise RateLimitError("Rate limit exceeded", retry_after_seconds=retry_after, limit=limit)

        # Opportunistic cleanup keeps the map bounded during local or single-instance use.
        if len(_buckets) > 5000:
            stale = [bucket_key for bucket_key, (bucket_window, _) in _buckets.items() if bucket_window < window - 2]
            for bucket_key in stale[:1000]:
                _buckets.pop(bucket_key, None)


def rate_limit_auth(request: Request) -> None:
    check_rate_limit(request, group="auth", limit=settings.auth_rate_limit_per_minute)


def rate_limit_paper_trading(request: Request) -> None:
    check_rate_limit(request, group="paper-trading", limit=settings.paper_trading_rate_limit_per_minute)


def rate_limit_assistant(request: Request) -> None:
    check_rate_limit(request, group="assistant", limit=settings.assistant_rate_limit_per_minute)


def reset_rate_limits() -> None:
    with _lock:
        _buckets.clear()
