"""Screener + snapshot ingest (PRD 20).

Snapshots are computed from the same live providers and stored in the local DB,
so screening runs over local data with no per-query external calls. Filters
compile to safe, whitelisted SQLAlchemy expressions (no arbitrary queries).
"""
from __future__ import annotations

from ..providers.base import Period
from ..db import CompanySnapshot, WatchlistItem, session_scope
from . import company, financials, prices
from ..valuation import service as valuation_service

# Numeric columns a user may filter/sort on (whitelist — prevents injection).
FILTERABLE = {
    "market_cap", "price", "pe", "price_to_fcf", "ev_ebitda", "dividend_yield",
    "net_debt", "revenue", "fcf", "fcf_margin", "fcf_conversion",
    "blended_fair_value", "margin_of_safety",
}
_OPS = {">": "__gt__", "<": "__lt__", ">=": "__ge__", "<=": "__le__", "=": "__eq__", "==": "__eq__"}

DEFAULT_UNIVERSE = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "BRK-B", "JPM",
    "UNH", "V", "MA", "HD", "COST", "LLY", "XOM", "JNJ", "PG", "AVGO",
    "ADBE", "CRM", "NFLX", "AMD", "KO", "PEP", "WMT",
]


def _normalize_tickers(tickers: list[str]) -> list[str]:
    out = []
    seen = set()
    for ticker in tickers:
        symbol = (ticker or "").strip().upper()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        out.append(symbol)
    return out


def build_snapshot(ticker: str) -> dict:
    """Compute a fresh snapshot for one ticker and upsert it."""
    ov = company.overview(ticker)
    km = ov["key_metrics"]
    profile = ov["profile"]
    val = valuation_service.valuate(ticker)
    inp = val["inputs"]
    fcf = inp.get("fcf0")
    revenue = inp.get("revenue")
    net_income = inp.get("net_income")

    fields = dict(
        ticker=ticker.upper(),
        name=profile.get("name"),
        sector=profile.get("sector"),
        industry=profile.get("industry"),
        price=km.get("price"),
        market_cap=km.get("market_cap"),
        pe=km.get("pe"),
        price_to_fcf=km.get("price_to_fcf"),
        ev_ebitda=km.get("ev_ebitda"),
        dividend_yield=km.get("dividend_yield"),
        net_debt=km.get("net_debt"),
        revenue=revenue,
        fcf=fcf,
        fcf_margin=(fcf / revenue) if (fcf is not None and revenue) else None,
        fcf_conversion=(fcf / net_income) if (fcf is not None and net_income and net_income > 0) else None,
        blended_fair_value=val.get("blended_fair_value"),
        margin_of_safety=val.get("margin_of_safety"),
    )
    with session_scope() as s:
        row = s.get(CompanySnapshot, ticker.upper())
        if row is None:
            row = CompanySnapshot(**fields)
            s.add(row)
        else:
            for k, v in fields.items():
                setattr(row, k, v)
    return fields


def ingest(tickers: list[str]) -> dict:
    done, failed = [], []
    for t in _normalize_tickers(tickers):
        try:
            build_snapshot(t)
            done.append(t)
        except Exception as exc:  # best-effort: one bad ticker doesn't sink the batch
            failed.append({"ticker": t, "error": str(exc)})
    return {"ingested": done, "failed": failed, "attempted": len(done) + len(failed)}


def seed_universe(tickers: list[str] | None = None) -> dict:
    """Ingest the starter local universe or an explicit replacement list."""
    return ingest(tickers or DEFAULT_UNIVERSE)


def tracked_tickers(*, include_default: bool = False, extra_tickers: list[str] | None = None) -> list[str]:
    with session_scope() as s:
        snapshot_tickers = [r[0] for r in s.query(CompanySnapshot.ticker).all()]
        watchlist_tickers = [r[0] for r in s.query(WatchlistItem.ticker).all()]
    base = snapshot_tickers + watchlist_tickers + (extra_tickers or [])
    if include_default:
        base += DEFAULT_UNIVERSE
    return _normalize_tickers(base)


def warm_ticker(ticker: str) -> dict:
    """Warm the primary analysis paths for one ticker and return per-domain status."""
    symbol = ticker.strip().upper()
    domains = []

    def run_domain(name: str, fn):
        try:
            fn()
            domains.append({"domain": name, "status": "ok"})
        except Exception as exc:  # best-effort warming, never abort on one section
            domains.append({"domain": name, "status": "failed", "error": str(exc)})

    run_domain("snapshot", lambda: build_snapshot(symbol))
    run_domain("company", lambda: company.overview(symbol))
    run_domain("cash_flow_analysis", lambda: financials.cash_flow_analysis(symbol, Period.ANNUAL))
    run_domain("valuation", lambda: valuation_service.valuate(symbol))
    run_domain("price_history", lambda: prices.price_history(symbol, range="1y", interval="1d"))

    failed = [domain for domain in domains if domain["status"] != "ok"]
    return {"ticker": symbol, "status": "failed" if failed else "ok", "domains": domains}


def warm_universe(*, tickers: list[str] | None = None, include_default: bool = False) -> dict:
    if tickers is not None:
        targets = _normalize_tickers(tickers + (DEFAULT_UNIVERSE if include_default else []))
    else:
        targets = tracked_tickers(include_default=include_default)
    details = [warm_ticker(ticker) for ticker in targets]
    warmed = [row["ticker"] for row in details if row["status"] == "ok"]
    failed = [row for row in details if row["status"] != "ok"]
    return {
        "tickers": len(targets),
        "warmed": len(warmed),
        "failed": len(failed),
        "warmed_tickers": warmed,
        "details": details,
    }


def universe() -> dict:
    with session_scope() as s:
        rows = s.query(CompanySnapshot.ticker).all()
        watchlist_rows = s.query(WatchlistItem.ticker).all()
    tickers = [r[0] for r in rows]
    watchlist_tickers = _normalize_tickers([r[0] for r in watchlist_rows])
    return {
        "count": len(tickers),
        "tickers": tickers,
        "watchlist_tickers": watchlist_tickers,
        "starter_universe_count": len(DEFAULT_UNIVERSE),
    }


def screen(filters: list[dict], sort: dict | None, limit: int = 100) -> dict:
    with session_scope() as s:
        q = s.query(CompanySnapshot)
        for f in filters or []:
            metric, op, value = f.get("metric"), f.get("op"), f.get("value")
            if metric not in FILTERABLE or op not in _OPS:
                continue
            col = getattr(CompanySnapshot, metric)
            q = q.filter(col.isnot(None)).filter(getattr(col, _OPS[op])(value))
        if sort and sort.get("metric") in FILTERABLE:
            col = getattr(CompanySnapshot, sort["metric"])
            q = q.order_by(col.desc() if sort.get("dir", "desc") == "desc" else col.asc())
        rows = q.limit(min(limit, 500)).all()
        results = [
            {c.name: getattr(r, c.name) for c in CompanySnapshot.__table__.columns if c.name != "updated_at"}
            for r in rows
        ]
    return {"results": results, "total": len(results)}
