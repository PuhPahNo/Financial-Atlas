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

    result = research.peers("AAPL")

    assert result["served_by"] == "finnhub"
    assert [p["ticker"] for p in result["peers"]] == ["MSFT", "GOOGL"]
    assert result["warnings"] == []  # FMP failure suppressed because Finnhub delivered


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
