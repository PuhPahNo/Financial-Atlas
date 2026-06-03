"""HTTP client with per-host token-bucket rate limiting (PRD 05 §5).

Each external host gets its own limiter sized to that provider's documented
limits, so we never exceed a provider's cap. On HTTP 429 we raise
``RateLimitError`` and the caller's fallback chain can move on.
"""
from __future__ import annotations

import threading
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from .errors import NotFoundError, ProviderError, RateLimitError


class _TokenBucket:
    """Simple thread-safe token bucket: ``rate`` tokens per second, capacity ``burst``."""

    def __init__(self, rate: float, burst: float):
        self.rate = rate
        self.capacity = burst
        self._tokens = burst
        self._updated = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        with self._lock:
            now = time.monotonic()
            self._tokens = min(self.capacity, self._tokens + (now - self._updated) * self.rate)
            self._updated = now
            if self._tokens < 1:
                wait = (1 - self._tokens) / self.rate
                time.sleep(wait)
                self._tokens = 0
            else:
                self._tokens -= 1


# Conservative per-host limits (well under documented caps; PRD 02 §5).
_LIMITS = {
    "data.sec.gov": _TokenBucket(rate=8, burst=8),
    "www.sec.gov": _TokenBucket(rate=8, burst=8),
    "efts.sec.gov": _TokenBucket(rate=5, burst=5),
    "query1.finance.yahoo.com": _TokenBucket(rate=4, burst=4),
    "query2.finance.yahoo.com": _TokenBucket(rate=4, burst=4),
}
_DEFAULT_LIMIT = _TokenBucket(rate=4, burst=4)

_client = httpx.Client(timeout=20.0, follow_redirects=True, headers={"Accept-Encoding": "gzip, deflate"})
_SENSITIVE_QUERY_KEYS = {"apikey", "api_key", "api-key", "access_token", "token", "secret", "password", "key"}


def _redact_url(url: str) -> str:
    try:
        parts = urlsplit(str(url))
    except ValueError:
        return "<redacted-url>"
    query = parse_qsl(parts.query, keep_blank_values=True)
    if not query:
        return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, parts.fragment))
    safe_query = [
        (key, "REDACTED" if key.lower() in _SENSITIVE_QUERY_KEYS else value)
        for key, value in query
    ]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(safe_query), parts.fragment))


def _request_url(resp: httpx.Response, fallback: str) -> str:
    try:
        return str(resp.request.url)
    except RuntimeError:
        return fallback


def get_json(url: str, *, headers: dict | None = None, params: dict | None = None, provider: str = "") -> dict:
    host = httpx.URL(url).host
    _LIMITS.get(host, _DEFAULT_LIMIT).acquire()
    try:
        resp = _client.get(url, headers=headers, params=params)
    except httpx.HTTPError as exc:
        raise ProviderError(f"{provider or host} request failed: {type(exc).__name__}") from exc

    if resp.status_code == 404:
        raise NotFoundError(f"{provider or host} returned 404 for {_redact_url(_request_url(resp, url))}")
    if resp.status_code == 429:
        raise RateLimitError(f"{provider or host} rate limited", retry_after_seconds=int(resp.headers.get("Retry-After", 30)))
    if resp.status_code >= 400:
        raise ProviderError(f"{provider or host} returned {resp.status_code}")
    try:
        return resp.json()
    except ValueError as exc:
        raise ProviderError(f"{provider or host} returned non-JSON response") from exc


def get_text(url: str, *, headers: dict | None = None, provider: str = "") -> str:
    """Fetch raw text (e.g. Form 4 XML). Same rate limiting / error mapping as get_json."""
    host = httpx.URL(url).host
    _LIMITS.get(host, _DEFAULT_LIMIT).acquire()
    try:
        resp = _client.get(url, headers=headers)
    except httpx.HTTPError as exc:
        raise ProviderError(f"{provider or host} request failed: {type(exc).__name__}") from exc
    if resp.status_code == 404:
        raise NotFoundError(f"{provider or host} returned 404 for {_redact_url(_request_url(resp, url))}")
    if resp.status_code == 429:
        raise RateLimitError(f"{provider or host} rate limited")
    if resp.status_code >= 400:
        raise ProviderError(f"{provider or host} returned {resp.status_code}")
    return resp.text
