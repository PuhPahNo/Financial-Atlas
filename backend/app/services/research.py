"""Research service — news, analyst snapshot, peers, multi-company compare.

Combines Finnhub (news, recommendation trends) and FMP (price targets, peers).
Everything degrades gracefully when a key is missing.
"""
from __future__ import annotations

from ..providers.registry import finnhub, fmp
from . import screener


def news(ticker: str) -> dict:
    if not finnhub.enabled:
        return {"articles": [], "available": False, "served_by": None}
    try:
        return {"articles": [a.model_dump() for a in finnhub.get_news(ticker)], "available": True, "served_by": "finnhub"}
    except Exception:
        return {"articles": [], "available": True, "served_by": "finnhub"}


def _rating_label(snap) -> str | None:
    counts = [snap.strong_buy, snap.buy, snap.hold, snap.sell, snap.strong_sell]
    if all(c is None for c in counts):
        return None
    sb, b, h, s, ss = (c or 0 for c in counts)
    total = sb + b + h + s + ss
    if total == 0:
        return None
    score = (sb * 2 + b * 1 + h * 0 + s * -1 + ss * -2) / total
    if score >= 1.5:
        return "Strong Buy"
    if score >= 0.5:
        return "Buy"
    if score > -0.5:
        return "Hold"
    if score > -1.5:
        return "Sell"
    return "Strong Sell"


def analyst(ticker: str) -> dict:
    snap = None
    if fmp.enabled:
        try:
            snap = fmp.get_price_target(ticker)
        except Exception:
            snap = None
    if finnhub.enabled:
        try:
            rec = finnhub.get_recommendation(ticker)
            if rec:
                if snap is None:
                    from ..providers.base import AnalystSnapshot
                    snap = AnalystSnapshot()
                snap.strong_buy = rec.get("strongBuy")
                snap.buy = rec.get("buy")
                snap.hold = rec.get("hold")
                snap.sell = rec.get("sell")
                snap.strong_sell = rec.get("strongSell")
        except Exception:
            pass
    if snap is None:
        return {"analyst": None, "available": bool(fmp.enabled or finnhub.enabled)}
    snap.rating = _rating_label(snap)
    return {"analyst": snap.model_dump(), "available": True}


def peers(ticker: str) -> dict:
    if fmp.enabled:
        try:
            rows = fmp.get_peers(ticker)
            if rows:
                return {"peers": [p.model_dump() for p in rows], "served_by": "fmp"}
        except Exception:
            pass
    if finnhub.enabled:
        try:
            from ..providers.base import Peer
            return {"peers": [Peer(ticker=t).model_dump() for t in finnhub.get_peers(ticker)], "served_by": "finnhub"}
        except Exception:
            pass
    return {"peers": [], "served_by": None}


def compare(tickers: list[str]) -> dict:
    """Key metrics for several tickers, side by side (reuses snapshot builder)."""
    out = []
    for t in tickers[:6]:
        try:
            out.append(screener.build_snapshot(t))
        except Exception as exc:
            out.append({"ticker": t.upper(), "error": str(exc)})
    return {"companies": out}
