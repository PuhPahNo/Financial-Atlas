from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.main import app
from app.services import market

client = TestClient(app)


def test_best_picks_degrades_when_database_is_unavailable(monkeypatch):
    def unavailable_session():
        raise OperationalError("select 1", {}, Exception("connection refused"))

    monkeypatch.setattr(market, "session_scope", unavailable_session)

    res = client.get("/api/v1/market/best-picks?limit=6")

    assert res.status_code == 200
    body = res.json()
    assert body["data"]["picks"] == []
    assert body["data"]["available"] is False
    assert body["data"]["warnings"][0]["code"] == "DATABASE_UNAVAILABLE"
