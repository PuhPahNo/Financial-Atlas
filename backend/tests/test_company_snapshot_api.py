from fastapi.testclient import TestClient

from app.main import app
from app.services import snapshot

client = TestClient(app)


def _patch_snapshot_dependencies(monkeypatch, *, fail_valuation: bool = False):
    monkeypatch.setattr(snapshot.company, "overview", lambda ticker: {
        "profile": {"ticker": ticker, "name": "Fixture Co", "exchange": "NYSE"},
        "key_metrics": {"price": 100, "market_cap": 1_000_000},
        "served_by": "fixture_profile",
    })

    def valuate(_: str):
        if fail_valuation:
            raise RuntimeError("valuation fixture failed")
        return {"current_price": 100, "blended_fair_value": 125, "margin_of_safety": 0.2}

    monkeypatch.setattr(snapshot.valuation_service, "valuate", valuate)
    monkeypatch.setattr(snapshot.financials, "cash_flow_analysis", lambda ticker, period: {
        "periods": [{"fiscal_year": 2025, "free_cash_flow": 50_000_000, "fcf_margin": 0.18}],
        "scorecard": {"overall_score": 75, "cards": []},
        "served_by": "fixture_financials",
    })
    monkeypatch.setattr(snapshot.research, "analyst", lambda ticker: {
        "analyst": {"rating": "Hold"},
        "available": True,
        "served_by": "fixture_analyst",
    })
    monkeypatch.setattr(snapshot.research, "news", lambda ticker: {
        "articles": [{"headline": "Fixture news"}],
        "available": True,
        "served_by": "fixture_news",
        "warnings": [],
    })
    monkeypatch.setattr(snapshot.research, "peers", lambda ticker: {
        "peers": [{"ticker": "MSFT"}],
        "served_by": "fixture_peers",
        "warnings": [],
    })
    monkeypatch.setattr(snapshot.prices, "price_history", lambda ticker, range, interval: (
        {"bars": [{"date": "2025-01-01", "close": 100}], "currency": "USD"},
        "fixture_prices",
    ))


def test_company_snapshot_composes_overview_sections(monkeypatch):
    _patch_snapshot_dependencies(monkeypatch)

    res = client.get("/api/v1/company/AAPL/snapshot")

    assert res.status_code == 200
    body = res.json()
    assert body["meta"]["ticker"] == "AAPL"
    assert body["meta"]["served_by"] == "fixture_profile"

    data = body["data"]
    assert data["company"]["profile"]["name"] == "Fixture Co"
    assert data["valuation"]["blended_fair_value"] == 125
    assert data["cash_flow_analysis"]["periods"][0]["fcf_margin"] == 0.18
    assert data["cash_flow_analysis"]["scorecard"]["overall_score"] == 75
    assert data["analyst"]["analyst"]["rating"] == "Hold"
    assert data["news"]["articles"][0]["headline"] == "Fixture news"
    assert data["peers"]["peers"][0]["ticker"] == "MSFT"
    assert data["prices"]["bars"][0]["close"] == 100
    assert data["warnings"] == []
    assert data["sections"]["prices"]["served_by"] == "fixture_prices"
    assert data["sections"]["prices"]["cache"]["status"] == "not_used"


def test_company_snapshot_promotes_research_warnings(monkeypatch):
    _patch_snapshot_dependencies(monkeypatch)
    monkeypatch.setattr(snapshot.research, "news", lambda ticker: {
        "articles": [],
        "available": False,
        "served_by": None,
        "warnings": [{
            "section": "news",
            "code": "PROVIDER_DISABLED",
            "message": "News data is unavailable because the optional provider is not configured.",
            "provider": "finnhub",
        }],
    })

    res = client.get("/api/v1/company/AAPL/snapshot")

    assert res.status_code == 200
    body = res.json()
    assert body["data"]["sections"]["news"]["available"] is False
    assert body["data"]["sections"]["news"]["warnings"][0]["code"] == "PROVIDER_DISABLED"
    assert body["meta"]["warnings"][0]["section"] == "news"


def test_company_snapshot_keeps_optional_section_failures_local(monkeypatch):
    _patch_snapshot_dependencies(monkeypatch, fail_valuation=True)

    res = client.get("/api/v1/company/AAPL/snapshot")

    assert res.status_code == 200
    data = res.json()["data"]
    assert data["company"]["profile"]["name"] == "Fixture Co"
    assert data["valuation"] is None
    assert data["sections"]["valuation"]["available"] is False
    assert data["warnings"] == [{
        "section": "valuation",
        "code": "SECTION_UNAVAILABLE",
        "message": "valuation data is unavailable right now.",
    }]


def test_company_snapshot_reports_section_cache_metadata(monkeypatch, tmp_path):
    _patch_snapshot_dependencies(monkeypatch)
    monkeypatch.setattr(snapshot.cache_service.settings, "cache_dir", tmp_path)
    monkeypatch.setattr(snapshot.cache_service.settings, "cache_enabled", True)

    def cached_price_history(ticker, range, interval):
        result = snapshot.cache_service.get_or_set(
            "fixture",
            f"prices:{ticker}:{range}:{interval}",
            ttl_seconds=60,
            loader=lambda: {"bars": [{"date": "2025-01-01", "close": 100}], "currency": "USD"},
        )
        return result.value, "fixture_prices"

    monkeypatch.setattr(snapshot.prices, "price_history", cached_price_history)

    first = client.get("/api/v1/company/AAPL/snapshot").json()
    second = client.get("/api/v1/company/AAPL/snapshot").json()

    assert first["data"]["sections"]["prices"]["cache"]["status"] == "miss"
    assert first["meta"]["as_of"] is not None
    assert second["data"]["sections"]["prices"]["cache"]["status"] == "hit"
    assert second["data"]["sections"]["prices"]["cache"]["hit_count"] == 1
