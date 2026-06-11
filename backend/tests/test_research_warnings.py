from fastapi.testclient import TestClient

from app.main import app
from app.services import research

client = TestClient(app)


def test_news_reports_disabled_provider_warning(monkeypatch):
    monkeypatch.setattr(research.finnhub, "key", "")

    result = research.news("AAPL")

    assert result["available"] is False
    assert result["articles"] == []
    assert result["warnings"][0]["code"] == "PROVIDER_DISABLED"
    assert result["warnings"][0]["provider"] == "finnhub"


def test_peers_logs_provider_errors_without_exposing_exception_text(monkeypatch):
    monkeypatch.setattr(research.fmp, "key", "fixture")
    monkeypatch.setattr(research.finnhub, "key", "")

    def fail(_: str):
        raise RuntimeError("secret-provider-token")

    monkeypatch.setattr(research.fmp, "get_peers", fail)

    result = research.peers("AAPL")

    messages = " ".join(warning["message"] for warning in result["warnings"])
    assert result["peers"] == []
    assert "secret-provider-token" not in messages
    assert any(warning["code"] == "PROVIDER_UNAVAILABLE" for warning in result["warnings"])


def test_peers_drops_fmp_note_when_finnhub_fallback_succeeds(monkeypatch):
    # FMP peers is premium-gated on the free plan; Finnhub (free) covers it. A working
    # fallback should leave NO provider note beside fully-populated peer data.
    monkeypatch.setattr(research.fmp, "key", "fixture")
    monkeypatch.setattr(research.finnhub, "key", "fixture")
    monkeypatch.setattr(research.fmp, "get_peers", lambda _t: (_ for _ in ()).throw(RuntimeError("premium endpoint")))
    monkeypatch.setattr(research.finnhub, "get_peers", lambda _t: ["MSFT", "GOOGL"])
    # Keep enrichment hermetic (no network) — covered separately below.
    monkeypatch.setattr(research, "_peer_name", lambda _t: None)
    monkeypatch.setattr(research, "_peer_market_cap", lambda _t: None)

    result = research.peers("AAPL")

    assert result["served_by"] == "finnhub"
    assert [p["ticker"] for p in result["peers"]] == ["MSFT", "GOOGL"]
    assert result["warnings"] == []  # FMP failure suppressed because Finnhub delivered


def test_finnhub_peers_enriched_with_name_and_market_cap(monkeypatch):
    # Finnhub returns bare tickers; we backfill name (SEC map) + market cap
    # (free-first: snapshot → EDGAR×Yahoo → FMP) so the table renders fully
    # instead of a column of dashes.
    from app.providers.base import Quote

    monkeypatch.setattr(research.cache.settings, "cache_enabled", False)
    monkeypatch.setattr(research.fmp, "key", "fixture")
    monkeypatch.setattr(research.finnhub, "key", "fixture")
    monkeypatch.setattr(research.fmp, "get_peers", lambda _t: [])  # premium / empty
    monkeypatch.setattr(research.finnhub, "get_peers", lambda _t: ["MSFT"])
    monkeypatch.setattr(research.sec_edgar, "resolve_cik", lambda t: {"cik": "0", "title": "Microsoft Corp"})
    monkeypatch.setattr(research, "_snapshot_market_cap", lambda _t: None)
    monkeypatch.setattr(research, "_computed_market_cap", lambda _t: None)
    monkeypatch.setattr(research.fmp, "get_quote", lambda t: Quote(price=400.0, market_cap=3_000_000_000_000))

    result = research.peers("AAPL")

    assert result["served_by"] == "finnhub"
    peer = result["peers"][0]
    assert peer["ticker"] == "MSFT"
    assert peer["name"] == "Microsoft Corp"
    assert peer["market_cap"] == 3_000_000_000_000
    assert result["warnings"] == []


def test_peer_market_cap_prefers_free_sources_over_fmp(monkeypatch):
    # FMP's quota is the scarcest resource: when a free source (screener snapshot,
    # EDGAR shares × Yahoo price) can answer, FMP must not be touched at all.
    monkeypatch.setattr(research.cache.settings, "cache_enabled", False)
    monkeypatch.setattr(research, "_snapshot_market_cap", lambda _t: 2_500_000_000_000)

    def explode(_t):
        raise AssertionError("FMP must not be called when a free source answers")

    monkeypatch.setattr(research.fmp, "get_quote", explode)
    assert research._peer_market_cap("MSFT") == 2_500_000_000_000


def test_peer_market_cap_cached_to_protect_fmp_quota(monkeypatch, tmp_path):
    # The 12h peer-market-cap cache must spare FMP's free quota: a second lookup
    # within the window hits the cache, not the API.
    from app.providers.base import Quote

    monkeypatch.setattr(research.cache.settings, "cache_dir", tmp_path)
    monkeypatch.setattr(research.cache.settings, "cache_enabled", True)
    monkeypatch.setattr(research.fmp, "key", "fixture")
    monkeypatch.setattr(research, "_snapshot_market_cap", lambda _t: None)
    monkeypatch.setattr(research, "_computed_market_cap", lambda _t: None)

    calls = {"n": 0}

    def counting_quote(_t):
        calls["n"] += 1
        return Quote(price=400.0, market_cap=3_000_000_000_000)

    monkeypatch.setattr(research.fmp, "get_quote", counting_quote)

    assert research._peer_market_cap("MSFT") == 3_000_000_000_000
    assert research._peer_market_cap("MSFT") == 3_000_000_000_000
    assert calls["n"] == 1  # second call served from cache, no extra FMP request


def test_analyst_drops_fmp_note_when_finnhub_rating_available(monkeypatch):
    monkeypatch.setattr(research.fmp, "key", "fixture")
    monkeypatch.setattr(research.finnhub, "key", "fixture")
    monkeypatch.setattr(research.fmp, "get_price_target", lambda _t: (_ for _ in ()).throw(RuntimeError("premium endpoint")))
    monkeypatch.setattr(research.finnhub, "get_recommendation", lambda _t: {
        "strongBuy": 10, "buy": 8, "hold": 3, "sell": 1, "strongSell": 0,
    })

    result = research.analyst("AAPL")

    assert result["available"] is True
    assert result["analyst"]["rating"] in {"Strong Buy", "Buy"}
    assert result["warnings"] == []  # FMP failure suppressed because Finnhub delivered a rating


def test_analyst_route_promotes_warnings_to_meta(monkeypatch):
    monkeypatch.setattr(research.fmp, "key", "")
    monkeypatch.setattr(research.finnhub, "key", "")

    res = client.get("/api/v1/analyst/AAPL")

    assert res.status_code == 200
    body = res.json()
    assert body["data"]["analyst"] is None
    assert body["meta"]["warnings"]
    assert body["meta"]["warnings"][0]["code"] == "PROVIDER_DISABLED"


def test_news_route_keeps_warning_in_data_and_meta(monkeypatch):
    monkeypatch.setattr(research.finnhub, "key", "")

    res = client.get("/api/v1/news/AAPL")

    assert res.status_code == 200
    body = res.json()
    assert body["data"]["warnings"] == body["meta"]["warnings"]
    assert body["data"]["warnings"][0]["section"] == "news"
