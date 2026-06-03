"""Watchlist service (PRD 21) — CRUD + computed price-vs-fair-value columns."""
from __future__ import annotations

from ..core.errors import NotFoundError, ValidationError
from ..db import CompanySnapshot, Watchlist, WatchlistItem, session_scope
from . import screener


def _item_view(s, ticker: str) -> dict:
    snap = s.get(CompanySnapshot, ticker.upper())
    price = snap.price if snap else None
    fv = snap.blended_fair_value if snap else None
    upside = ((fv - price) / price) if (fv and price) else None
    return {
        "ticker": ticker.upper(),
        "name": snap.name if snap else None,
        "price": price,
        "blended_fair_value": fv,
        "upside_pct": upside,
        "margin_of_safety": snap.margin_of_safety if snap else None,
        "last_updated": snap.updated_at.isoformat() if (snap and snap.updated_at) else None,
        "pending": snap is None,
    }


def list_watchlists() -> dict:
    with session_scope() as s:
        lists = s.query(Watchlist).order_by(Watchlist.created_at.asc()).all()
        out = [{
            "id": wl.id,
            "name": wl.name,
            "items": [_item_view(s, it.ticker) for it in wl.items],
        } for wl in lists]
    return {"watchlists": out}


def create_watchlist(name: str) -> dict:
    if not name or not name.strip():
        raise ValidationError("Watchlist name is required")
    with session_scope() as s:
        wl = Watchlist(name=name.strip())
        s.add(wl)
        s.flush()
        return {"id": wl.id, "name": wl.name, "items": []}


def delete_watchlist(watchlist_id: int) -> dict:
    with session_scope() as s:
        wl = s.get(Watchlist, watchlist_id)
        if wl is None:
            raise NotFoundError(f"Watchlist {watchlist_id} not found")
        s.delete(wl)
    return {"deleted": watchlist_id}


def add_item(watchlist_id: int, ticker: str) -> dict:
    ticker = ticker.strip().upper()
    if not ticker:
        raise ValidationError("Ticker is required")
    # Ensure a snapshot exists so computed columns populate (best-effort).
    try:
        screener.build_snapshot(ticker)
    except Exception:
        pass
    with session_scope() as s:
        wl = s.get(Watchlist, watchlist_id)
        if wl is None:
            raise NotFoundError(f"Watchlist {watchlist_id} not found")
        exists = s.query(WatchlistItem).filter_by(watchlist_id=watchlist_id, ticker=ticker).first()
        if not exists:
            s.add(WatchlistItem(watchlist_id=watchlist_id, ticker=ticker))
        view = _item_view(s, ticker)
    return view


def remove_item(watchlist_id: int, ticker: str) -> dict:
    with session_scope() as s:
        item = s.query(WatchlistItem).filter_by(watchlist_id=watchlist_id, ticker=ticker.upper()).first()
        if item:
            s.delete(item)
    return {"removed": ticker.upper()}
