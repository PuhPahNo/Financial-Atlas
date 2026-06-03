"""REST API routes (PRD 04). Thin layer: validate, call services, wrap envelope."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Query
from fastapi.responses import HTMLResponse

from ..providers.base import Period
from ..providers.registry import sec_edgar
from ..services import company, financials, prices, snapshot
from ..services import ownership as ownership_service
from ..services import filings as filings_service
from ..services import screener as screener_service
from ..services import watchlists as watchlist_service
from ..services import market as market_service
from ..services import research as research_service

router = APIRouter(prefix="/api/v1")


def envelope(
    data: Any,
    *,
    ticker: str | None = None,
    served_by: str | None = None,
    stale: bool = False,
    as_of: str | None = None,
    warnings: list[dict] | None = None,
) -> dict:
    meta = {"ticker": ticker, "served_by": served_by, "stale": stale}
    if as_of is not None:
        meta["as_of"] = as_of
    if warnings:
        meta["warnings"] = warnings
    return {"data": data, "meta": meta}


def _period(value: str) -> Period:
    return Period.QUARTER if value == "quarter" else Period.ANNUAL


@router.get("/search")
def search(q: str = Query(..., min_length=1)):
    return envelope(sec_edgar.search_tickers(q, limit=10))


@router.get("/company/{ticker}")
def company_overview(ticker: str):
    result = company.overview(ticker)
    return envelope(result, ticker=ticker.upper(), served_by=result.get("served_by"))


@router.get("/company/{ticker}/snapshot")
def company_snapshot(ticker: str, period: str = "annual", range: str = "1y", interval: str = "1d"):
    result = snapshot.overview_snapshot(ticker, period=_period(period), price_range=range, interval=interval)
    served_by = result.get("sections", {}).get("company", {}).get("served_by")
    stale = any(section.get("stale") for section in result.get("sections", {}).values())
    return envelope(
        result,
        ticker=ticker.upper(),
        served_by=served_by,
        stale=stale,
        as_of=result.get("as_of"),
        warnings=result.get("warnings"),
    )


@router.get("/prices/{ticker}")
def price_history(ticker: str, range: str = "1y", interval: str = "1d"):
    data, served_by = prices.price_history(ticker, range=range, interval=interval)
    return envelope(data, ticker=ticker.upper(), served_by=served_by)


@router.get("/financials/{ticker}/income")
def income(ticker: str, period: str = "annual"):
    rows, served_by = financials.statements(ticker, "income", _period(period))
    return envelope({"statements": rows, "currency": "USD"}, ticker=ticker.upper(), served_by=served_by)


@router.get("/financials/{ticker}/balance-sheet")
def balance_sheet(ticker: str, period: str = "annual"):
    rows, served_by = financials.statements(ticker, "balance", _period(period))
    return envelope({"statements": rows, "currency": "USD"}, ticker=ticker.upper(), served_by=served_by)


@router.get("/financials/{ticker}/cash-flow")
def cash_flow(ticker: str, period: str = "annual"):
    rows, served_by = financials.statements(ticker, "cashflow", _period(period))
    return envelope({"statements": rows, "currency": "USD"}, ticker=ticker.upper(), served_by=served_by)


@router.get("/financials/{ticker}/cash-flow-analysis")
def cash_flow_analysis(ticker: str, period: str = "annual"):
    result = financials.cash_flow_analysis(ticker, _period(period))
    return envelope({"periods": result["periods"], "scorecard": result["scorecard"], "currency": "USD"},
                    ticker=ticker.upper(), served_by=result["served_by"])


@router.get("/ownership/{ticker}/insiders")
def insiders(ticker: str):
    result = ownership_service.insiders(ticker)
    return envelope({"transactions": result["transactions"], "summary": result["summary"]},
                    ticker=ticker.upper(), served_by=result["served_by"])


@router.get("/ownership/{ticker}/institutions")
def institutions(ticker: str):
    result = ownership_service.institutions(ticker)
    return envelope({"large_stakes": result["large_stakes"], "note": result["note"]},
                    ticker=ticker.upper(), served_by=result["served_by"])


@router.get("/filings/document")
def filing_document(url: str = Query(...)):
    return envelope(filings_service.document(url), served_by="sec_edgar")


@router.get("/filings/document/raw", response_class=HTMLResponse)
def filing_document_raw(url: str = Query(...)):
    # Cleaned filing HTML served same-origin so the reader iframe renders it natively.
    return HTMLResponse(content=filings_service.document(url)["html"])


@router.get("/filings/{ticker}")
def filings(ticker: str, forms: str | None = Query(default=None)):
    form_list = [f.strip() for f in forms.split(",")] if forms else None
    result = filings_service.filings(ticker, forms=form_list, limit=60)
    return envelope({"filings": result["filings"]}, ticker=ticker.upper(), served_by=result["served_by"])


# --- Market & research -----------------------------------------------------
@router.get("/market/movers")
def market_movers():
    return envelope(market_service.movers())


@router.get("/market/context")
def market_context():
    return envelope(market_service.context())


@router.get("/market/best-picks")
def market_best_picks(limit: int = 8):
    return envelope(market_service.best_picks(limit))


@router.get("/news/{ticker}")
def news(ticker: str):
    r = research_service.news(ticker)
    return envelope(
        {"articles": r["articles"], "available": r["available"], "warnings": r.get("warnings", [])},
        ticker=ticker.upper(),
        served_by=r["served_by"],
        warnings=r.get("warnings"),
    )


@router.get("/analyst/{ticker}")
def analyst(ticker: str):
    result = research_service.analyst(ticker)
    return envelope(result, ticker=ticker.upper(), warnings=result.get("warnings"))


@router.get("/peers/{ticker}")
def peers(ticker: str):
    r = research_service.peers(ticker)
    return envelope(
        {"peers": r["peers"], "warnings": r.get("warnings", [])},
        ticker=ticker.upper(),
        served_by=r["served_by"],
        warnings=r.get("warnings"),
    )


@router.get("/compare")
def compare(tickers: str = Query(...)):
    tk = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    return envelope(research_service.compare(tk))


@router.get("/valuation/{ticker}")
def valuation(ticker: str):
    from ..valuation import service as valuation_service
    result = valuation_service.valuate(ticker)
    valuation_service.record_result(ticker, result)
    return envelope(result, ticker=ticker.upper(), served_by="derived")


@router.post("/valuation/{ticker}")
def valuation_custom(ticker: str, body: dict = Body(default_factory=dict)):
    from ..valuation import service as valuation_service
    result = valuation_service.valuate(ticker, assumptions=body.get("assumptions"), weights=body.get("weights"))
    valuation_service.record_result(ticker, result, weights=body.get("weights"))
    return envelope(result, ticker=ticker.upper(), served_by="derived")


@router.get("/valuation/{ticker}/history")
def valuation_history(ticker: str, limit: int = 20):
    from ..valuation import service as valuation_service
    return envelope(valuation_service.valuation_history(ticker, limit=limit), ticker=ticker.upper(), served_by="local")


# --- Screener -------------------------------------------------------------
@router.get("/screener/universe")
def screener_universe():
    return envelope(screener_service.universe())


@router.post("/screener/ingest")
def screener_ingest(body: dict = Body(default_factory=dict)):
    tickers = body.get("tickers") or []
    return envelope(screener_service.ingest(tickers))


@router.post("/screener/seed")
def screener_seed(body: dict = Body(default_factory=dict)):
    tickers = body.get("tickers")
    return envelope(screener_service.seed_universe(tickers))


@router.post("/screener/warm")
def screener_warm(body: dict = Body(default_factory=dict)):
    return envelope(screener_service.warm_universe(
        tickers=body.get("tickers"),
        include_default=bool(body.get("include_default", False)),
    ))


@router.post("/screener")
def screener_run(body: dict = Body(default_factory=dict)):
    return envelope(screener_service.screen(body.get("filters", []), body.get("sort"), body.get("limit", 100)))


# --- Watchlists -----------------------------------------------------------
@router.get("/watchlists")
def watchlists_list():
    return envelope(watchlist_service.list_watchlists())


@router.post("/watchlists")
def watchlists_create(body: dict = Body(default_factory=dict)):
    return envelope(watchlist_service.create_watchlist(body.get("name", "")))


@router.delete("/watchlists/{watchlist_id}")
def watchlists_delete(watchlist_id: int):
    return envelope(watchlist_service.delete_watchlist(watchlist_id))


@router.post("/watchlists/{watchlist_id}/items")
def watchlist_add_item(watchlist_id: int, body: dict = Body(default_factory=dict)):
    return envelope(watchlist_service.add_item(watchlist_id, body.get("ticker", "")))


@router.delete("/watchlists/{watchlist_id}/items/{ticker}")
def watchlist_remove_item(watchlist_id: int, ticker: str):
    return envelope(watchlist_service.remove_item(watchlist_id, ticker))
