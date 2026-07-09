import httpx
import pytest

from app.core import http
from app.core.errors import NotFoundError, ProviderError, RateLimitError


class _NoopLimiter:
    def acquire(self):
        return None


class _Client:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error

    def get(self, *_args, **_kwargs):
        if self.error:
            raise self.error
        return self.response


@pytest.fixture(autouse=True)
def no_rate_limit(monkeypatch):
    monkeypatch.setattr(http, "_DEFAULT_LIMIT", _NoopLimiter())


@pytest.mark.parametrize("getter", [http.get_json, http.get_text])
def test_http_getters_share_redacted_404_mapping(monkeypatch, getter):
    url = "https://example.com/missing?apikey=secret"
    response = httpx.Response(404, request=httpx.Request("GET", url))
    monkeypatch.setattr(http, "_client", _Client(response=response))

    with pytest.raises(NotFoundError) as exc_info:
        getter(url, provider="example")

    assert "secret" not in exc_info.value.message
    assert "apikey=REDACTED" in exc_info.value.message


@pytest.mark.parametrize("getter", [http.get_json, http.get_text])
def test_http_getters_share_retry_after_mapping(monkeypatch, getter):
    url = "https://example.com/limited"
    response = httpx.Response(429, headers={"Retry-After": "7"}, request=httpx.Request("GET", url))
    monkeypatch.setattr(http, "_client", _Client(response=response))

    with pytest.raises(RateLimitError) as exc_info:
        getter(url, provider="example")

    assert exc_info.value.context["retry_after_seconds"] == 7


def test_invalid_retry_after_falls_back_to_thirty_seconds(monkeypatch):
    url = "https://example.com/limited"
    response = httpx.Response(429, headers={"Retry-After": "tomorrow"}, request=httpx.Request("GET", url))
    monkeypatch.setattr(http, "_client", _Client(response=response))

    with pytest.raises(RateLimitError) as exc_info:
        http.get_json(url)

    assert exc_info.value.context["retry_after_seconds"] == 30


@pytest.mark.parametrize("getter", [http.get_json, http.get_text])
def test_http_getters_share_transport_error_mapping(monkeypatch, getter):
    url = "https://example.com/failure"
    monkeypatch.setattr(http, "_client", _Client(error=httpx.ConnectError("offline")))

    with pytest.raises(ProviderError, match="ConnectError"):
        getter(url, provider="example")
