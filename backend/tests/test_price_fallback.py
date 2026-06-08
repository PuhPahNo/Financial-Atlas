"""Price provider resilience: Stooq fallback + chain/Yahoo hardening.

These cover the failure mode where Yahoo (the primary price/quote source) is
blocked or returns junk, ensuring the request degrades to the keyless fallback
instead of surfacing a 500.
"""
import pytest

from app.core.errors import NotFoundError, ProviderError
from app.providers import registry
from app.providers.stooq import StooqProvider, _parse_csv, _symbol
from app.providers.yahoo import YahooProvider

_CSV = (
    "Date,Open,High,Low,Close,Volume\n"
    "2025-01-02,10.0,11.0,9.5,10.5,1000\n"
    "2025-01-03,10.5,12.0,10.4,11.8,2000\n"
)


def test_stooq_parses_csv_into_bars():
    bars = _parse_csv(_CSV, "aapl.us")
    assert len(bars) == 2
    assert bars[-1].close == 11.8
    assert bars[-1].volume == 2000
    assert bars[0].adjusted_close == 10.5  # close reused as adjusted_close


def test_stooq_rejects_non_csv_body():
    # Unknown symbol / throttle page → ProviderError (chain skips, never 500).
    with pytest.raises(ProviderError):
        _parse_csv("No data", "zzzz.us")


def test_stooq_symbol_normalisation():
    assert _symbol("AAPL") == "aapl.us"
    assert _symbol("BRK.B") == "brk-b.us"


def test_stooq_quote_derived_from_bars(monkeypatch):
    monkeypatch.setattr(StooqProvider, "_bars", lambda self, sym, **kw: _parse_csv(_CSV, sym))
    q = StooqProvider().get_quote("AAPL")
    assert q.price == 11.8
    assert q.previous_close == 10.5
    assert q.change_abs == pytest.approx(1.3)
    assert q.week52_high == 12.0
    assert q.week52_low == 9.5


def test_yahoo_unexpected_body_is_provider_error():
    # A non-dict body (e.g. an error envelope) must degrade, not raise AttributeError.
    with pytest.raises(ProviderError):
        YahooProvider._result(["unexpected"], "AAPL")
    with pytest.raises(ProviderError):
        YahooProvider._parse_result(None, "AAPL")


class _BadProvider:
    name = "bad"

    def get(self, *a, **k):
        raise KeyError("malformed upstream body")  # a non-AtlasError, like a junk Yahoo body


class _GoodProvider:
    name = "good"

    def get(self, *a, **k):
        return "ok"


def test_run_chain_falls_through_unexpected_exception(monkeypatch):
    monkeypatch.setitem(registry.CHAINS, "_test_domain", [_BadProvider(), _GoodProvider()])
    result, served_by = registry.run_chain("_test_domain", "get")
    assert result == "ok"
    assert served_by == "good"


def test_run_chain_still_propagates_not_found(monkeypatch):
    class _NotFound:
        name = "nf"

        def get(self, *a, **k):
            raise NotFoundError("ticker missing")

    monkeypatch.setitem(registry.CHAINS, "_test_domain", [_NotFound(), _GoodProvider()])
    with pytest.raises(NotFoundError):
        registry.run_chain("_test_domain", "get")
