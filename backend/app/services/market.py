"""Market-level data for the dashboard (PRD: Home dashboard).

Movers come from FMP (market-wide) with a universe fallback; market context
(indices + 10Y yield) comes from Yahoo (keyless); best picks reuse the local
snapshot table sorted by margin of safety.
"""
from __future__ import annotations

from sqlalchemy.exc import SQLAlchemyError

from ..core import cache
from ..db import CompanySnapshot, session_scope
from ..providers.base import Interval
from ..providers.registry import fmp, yahoo

_INDICES = [("^GSPC", "S&P 500"), ("^IXIC", "Nasdaq"), ("^TNX", "10Y Treasury")]


def movers() -> dict:
    """Market-wide gainers/losers/actives (FMP). Falls back to universe movers."""
    if fmp.enabled:
        try:
            return {
                "scope": "market",
                "gainers": [m.model_dump() for m in fmp.gainers()],
                "losers": [m.model_dump() for m in fmp.losers()],
                "actives": [m.model_dump() for m in fmp.actives()],
            }
        except Exception:
            pass
    # fallback: movers within the ingested universe (by stored price change is N/A,
    # so just surface the universe ranked by margin of safety extremes).
    with session_scope() as s:
        rows = s.query(CompanySnapshot).all()
        data = [{"ticker": r.ticker, "name": r.name, "price": r.price} for r in rows]
    return {"scope": "universe", "gainers": data, "losers": [], "actives": []}


def context() -> dict:
    """Index + yield mini-series for the market-context panel (Yahoo, keyless)."""
    def load():
        out = []
        for symbol, label in _INDICES:
            try:
                bars = yahoo.get_price_history(symbol, range="1m", interval=Interval.DAY)
                closes = [b.close for b in bars if b.close is not None]
                if not closes:
                    continue
                change_pct = ((closes[-1] - closes[-2]) / closes[-2]) if len(closes) >= 2 else None
                out.append({"symbol": symbol, "label": label, "price": closes[-1],
                            "change_pct": change_pct, "points": closes[-22:]})
            except Exception:
                continue
        return out
    return {"indices": cache.get_or_set("market", "context", ttl_seconds=900, loader=load).value}


def best_picks(limit: int = 8) -> dict:
    """Most-undervalued names from the local universe (highest margin of safety)."""
    try:
        with session_scope() as s:
            rows = (s.query(CompanySnapshot)
                    .filter(CompanySnapshot.margin_of_safety.isnot(None))
                    .order_by(CompanySnapshot.margin_of_safety.desc())
                    .limit(limit).all())
            return {"picks": [{
                "ticker": r.ticker, "name": r.name, "price": r.price,
                "blended_fair_value": r.blended_fair_value, "margin_of_safety": r.margin_of_safety,
                "fcf_margin": r.fcf_margin,
            } for r in rows]}
    except SQLAlchemyError:
        return {
            "picks": [],
            "available": False,
            "warnings": [{
                "section": "best_picks",
                "code": "DATABASE_UNAVAILABLE",
                "message": "Best picks are temporarily unavailable while the database reconnects.",
            }],
        }
