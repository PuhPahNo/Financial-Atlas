from fastapi.testclient import TestClient

from app.main import app
from app.valuation import service as valuation_service

client = TestClient(app)


def test_valuation_route_records_retrievable_history(monkeypatch):
    def fake_valuate(ticker, *, assumptions=None, weights=None):
        return {
            "ticker": ticker.upper(),
            "current_price": 100.0,
            "models": [{"model": "dcf", "applicable": True, "fair_value_per_share": 125.0}],
            "blended_fair_value": 125.0,
            "applied_weights": {"dcf": 1.0},
            "scenarios": {"bear": 100.0, "base": 125.0, "bull": 150.0},
            "margin_of_safety": 0.2,
            "assumptions": assumptions or {"discount_rate": 0.1},
            "inputs": {},
            "diagnostics": {
                "models": [],
                "blend": {"renormalized": False},
                "sensitivity": {},
                "history_available": True,
            },
        }

    monkeypatch.setattr(valuation_service, "valuate", fake_valuate)

    res = client.post("/api/v1/valuation/TST", json={"assumptions": {"discount_rate": 0.11}})
    assert res.status_code == 200
    assert res.json()["data"]["diagnostics"]["history_available"] is True

    history = client.get("/api/v1/valuation/TST/history").json()["data"]["results"]
    assert history
    assert history[0]["ticker"] == "TST"
    assert history[0]["blended_fair_value"] == 125.0
    assert history[0]["assumptions"]["discount_rate"] == 0.11

    duplicate = client.post("/api/v1/valuation/TST", json={"assumptions": {"discount_rate": 0.11}})
    assert duplicate.status_code == 200
    deduped = client.get("/api/v1/valuation/TST/history").json()["data"]["results"]
    assert len(deduped) == 1
