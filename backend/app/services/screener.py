"""Screener + snapshot ingest (PRD 20).

Snapshots are computed from the same live providers and stored in the local DB,
so screening runs over local data with no per-query external calls. Filters
compile to safe, whitelisted SQLAlchemy expressions (no arbitrary queries).
"""
from __future__ import annotations

from ..db import CompanySnapshot, session_scope
from ..providers.registry import run_chain
from . import company
from ..valuation import service as valuation_service

# Numeric columns a user may filter/sort on (whitelist — prevents injection).
FILTERABLE = {
    "market_cap", "price", "pe", "price_to_fcf", "ev_ebitda", "dividend_yield",
    "net_debt", "revenue", "fcf", "fcf_margin", "fcf_conversion",
    "blended_fair_value", "margin_of_safety",
}
_OPS = {">": "__gt__", "<": "__lt__", ">=": "__ge__", "<=": "__le__", "=": "__eq__", "==": "__eq__"}


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
    for t in tickers:
        try:
            build_snapshot(t)
            done.append(t.upper())
        except Exception as exc:  # best-effort: one bad ticker doesn't sink the batch
            failed.append({"ticker": t.upper(), "error": str(exc)})
    return {"ingested": done, "failed": failed}


def universe() -> dict:
    with session_scope() as s:
        rows = s.query(CompanySnapshot.ticker).all()
    return {"count": len(rows), "tickers": [r[0] for r in rows]}


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
