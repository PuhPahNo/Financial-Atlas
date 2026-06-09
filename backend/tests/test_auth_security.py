from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.rate_limit import reset_rate_limits
from app.main import app
from auth_helpers import authenticate


def test_protected_workspaces_require_login():
    client = TestClient(app)

    paper = client.get("/api/v1/paper-trading/categories")
    assert paper.status_code == 401
    assert paper.json()["error"]["code"] == "UNAUTHORIZED"

    watchlists = client.get("/api/v1/watchlists")
    assert watchlists.status_code == 401
    assert watchlists.json()["error"]["code"] == "UNAUTHORIZED"

    health = client.get("/health")
    assert health.status_code == 200


def test_security_headers_present_on_responses():
    client = TestClient(app)
    res = client.get("/health")
    assert res.headers["X-Content-Type-Options"] == "nosniff"
    assert res.headers["X-Frame-Options"] == "DENY"
    assert res.headers["Content-Security-Policy"] == "frame-ancestors 'none'"
    assert res.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


def test_authenticated_user_can_read_protected_workspace():
    client = authenticate(TestClient(app))
    res = client.get("/api/v1/paper-trading/categories")
    assert res.status_code == 200
    assert res.json()["data"]["categories"]


def test_assistant_rate_limit_blocks_excess_usage(monkeypatch):
    monkeypatch.setattr(settings, "assistant_rate_limit_per_minute", 2)
    reset_rate_limits()
    client = authenticate(TestClient(app))

    assert client.post("/api/v1/assistant/sessions", json={"title": "Rate Limit 1"}).status_code == 200
    assert client.post("/api/v1/assistant/sessions", json={"title": "Rate Limit 2"}).status_code == 200
    limited = client.post("/api/v1/assistant/sessions", json={"title": "Rate Limit 3"})
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "RATE_LIMITED"
