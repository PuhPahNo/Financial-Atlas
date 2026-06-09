"""REST API routes (PRD 04). Thin layer: validate, call services, wrap envelope."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from ..core.deps import require_edit_access
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


# --- Request bodies ---------------------------------------------------------
# Every mutating endpoint takes a typed model so malformed/oversized payloads are
# rejected at the framework boundary instead of deep inside a service.

_TICKER_FIELD = Field(min_length=1, max_length=12)


class ValuationBody(BaseModel):
    assumptions: dict[str, float | None] | None = None
    weights: dict[str, float] | None = None


class TickerBatchBody(BaseModel):
    tickers: list[str] = Field(default_factory=list, max_length=600)


class SeedBody(BaseModel):
    tickers: list[str] | None = Field(default=None, max_length=600)


class WarmBody(BaseModel):
    tickers: list[str] | None = Field(default=None, max_length=600)
    include_default: bool = False


class ScreenFilter(BaseModel):
    metric: str
    op: str
    value: float


class ScreenSort(BaseModel):
    metric: str
    dir: str = "desc"


class ScreenBody(BaseModel):
    filters: list[ScreenFilter] = Field(default_factory=list, max_length=50)
    sort: ScreenSort | None = None
    limit: int = Field(default=100, ge=1, le=500)


class WatchlistCreateBody(BaseModel):
    name: str = Field(default="", max_length=120)


class WatchlistItemBody(BaseModel):
    ticker: str = _TICKER_FIELD


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
def market_best_picks(limit: int = Query(default=8, ge=1, le=50)):
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


@router.post("/valuation/{ticker}", dependencies=[Depends(require_edit_access)])
def valuation_custom(ticker: str, body: ValuationBody = ValuationBody()):
    from ..valuation import service as valuation_service
    result = valuation_service.valuate(ticker, assumptions=body.assumptions, weights=body.weights)
    valuation_service.record_result(ticker, result, weights=body.weights)
    return envelope(result, ticker=ticker.upper(), served_by="derived")


@router.get("/valuation/{ticker}/history")
def valuation_history(ticker: str, limit: int = Query(default=20, ge=1, le=200)):
    from ..valuation import service as valuation_service
    return envelope(valuation_service.valuation_history(ticker, limit=limit), ticker=ticker.upper(), served_by="local")


# --- Screener -------------------------------------------------------------
@router.get("/screener/universe")
def screener_universe():
    return envelope(screener_service.universe())


@router.post("/screener/ingest", dependencies=[Depends(require_edit_access)])
def screener_ingest(body: TickerBatchBody = TickerBatchBody()):
    return envelope(screener_service.ingest(body.tickers))


@router.post("/screener/seed", dependencies=[Depends(require_edit_access)])
def screener_seed(body: SeedBody = SeedBody()):
    return envelope(screener_service.seed_universe(body.tickers))


@router.post("/screener/warm", dependencies=[Depends(require_edit_access)])
def screener_warm(body: WarmBody = WarmBody()):
    return envelope(screener_service.warm_universe(
        tickers=body.tickers,
        include_default=body.include_default,
    ))


@router.post("/screener")
def screener_run(body: ScreenBody = ScreenBody()):
    return envelope(screener_service.screen(
        [f.model_dump() for f in body.filters],
        body.sort.model_dump() if body.sort else None,
        body.limit,
    ))


# --- Watchlists -----------------------------------------------------------
@router.get("/watchlists", dependencies=[Depends(require_edit_access)])
def watchlists_list():
    return envelope(watchlist_service.list_watchlists())


@router.post("/watchlists", dependencies=[Depends(require_edit_access)])
def watchlists_create(body: WatchlistCreateBody = WatchlistCreateBody()):
    return envelope(watchlist_service.create_watchlist(body.name))


@router.delete("/watchlists/{watchlist_id}", dependencies=[Depends(require_edit_access)])
def watchlists_delete(watchlist_id: int):
    return envelope(watchlist_service.delete_watchlist(watchlist_id))


@router.post("/watchlists/{watchlist_id}/items", dependencies=[Depends(require_edit_access)])
def watchlist_add_item(watchlist_id: int, body: WatchlistItemBody):
    return envelope(watchlist_service.add_item(watchlist_id, body.ticker))


@router.delete("/watchlists/{watchlist_id}/items/{ticker}", dependencies=[Depends(require_edit_access)])
def watchlist_remove_item(watchlist_id: int, ticker: str):
    return envelope(watchlist_service.remove_item(watchlist_id, ticker))
