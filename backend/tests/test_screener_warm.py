from fastapi.testclient import TestClient

from app.db import CompanySnapshot, Watchlist, WatchlistItem, session_scope
from app.jobs import refresh
from app.main import app
from app.services import screener
from auth_helpers import authenticate

client = authenticate(TestClient(app))


def test_tracked_tickers_include_snapshots_watchlists_and_extras_without_duplicates():
    with session_scope() as session:
        session.add(CompanySnapshot(ticker="AAA", name="AAA Co"))
        watchlist = Watchlist(name="Test Warm Watchlist")
        session.add(watchlist)
        session.flush()
        session.add(WatchlistItem(watchlist_id=watchlist.id, ticker="BBB"))

    tickers = screener.tracked_tickers(extra_tickers=["AAA", "CCC"])

    for ticker in ["AAA", "BBB", "CCC"]:
        assert tickers.count(ticker) == 1
    assert tickers.index("BBB") < tickers.index("CCC")


def test_warm_universe_logs_failures_without_aborting(monkeypatch):
    def fake_warm(ticker: str):
        if ticker == "FAIL":
            return {
                "ticker": ticker,
                "status": "failed",
                "domains": [{"domain": "snapshot", "status": "failed", "error": "fixture failure"}],
            }
        return {"ticker": ticker, "status": "ok", "domains": [{"domain": "snapshot", "status": "ok"}]}

    monkeypatch.setattr(screener, "warm_ticker", fake_warm)

    result = screener.warm_universe(tickers=["AAA", "FAIL"])

    assert result["tickers"] == 2
    assert result["warmed"] == 1
    assert result["failed"] == 1
    assert result["details"][1]["domains"][0]["error"] == "fixture failure"


def test_refresh_job_uses_tracked_tickers_and_returns_details(monkeypatch):
    monkeypatch.setattr(refresh, "init_db", lambda: None)
    monkeypatch.setattr(screener, "tracked_tickers", lambda include_default=False: ["AAA", "FAIL"])

    def fake_warm(ticker: str):
        if ticker == "FAIL":
            return {
                "ticker": ticker,
                "status": "failed",
                "domains": [{"domain": "valuation", "status": "failed", "error": "bad input"}],
            }
        return {"ticker": ticker, "status": "ok", "domains": [{"domain": "valuation", "status": "ok"}]}

    monkeypatch.setattr(screener, "warm_ticker", fake_warm)

    result = refresh.run()

    assert result["tickers"] == 2
    assert result["refreshed"] == 1
    assert result["failed"] == 1
    assert result["details"][0]["ticker"] == "AAA"


def test_screener_seed_endpoint_uses_default_universe(monkeypatch):
    monkeypatch.setattr(screener, "DEFAULT_UNIVERSE", ["AAA", "BBB"])
    monkeypatch.setattr(screener, "build_snapshot", lambda ticker: {"ticker": ticker})

    res = client.post("/api/v1/screener/seed", json={})

    assert res.status_code == 200
    data = res.json()["data"]
    assert data["attempted"] == 2
    assert data["ingested"] == ["AAA", "BBB"]
