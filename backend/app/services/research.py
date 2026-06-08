"""Research service — news, analyst snapshot, peers, multi-company compare.

Combines Finnhub (news, recommendation trends) and FMP (price targets, peers).
Everything degrades gracefully when a key is missing.
"""
from __future__ import annotations

import logging

from ..providers.registry import finnhub, fmp, sec_edgar
from . import screener

log = logging.getLogger(__name__)


def _peer_name(ticker: str) -> str | None:
    """Company name from SEC's cached ticker->CIK map (free, no extra network)."""
    try:
        return sec_edgar.resolve_cik(ticker).get("title")
    except Exception:
        return None


def _peer_market_cap(ticker: str) -> float | None:
    """Market cap from FMP's free quote endpoint (best-effort, short-cached)."""
    if not fmp.enabled:
        return None
    try:
        return fmp.get_quote(ticker).market_cap
    except Exception:
        return None


def _enrich_peers(tickers: list[str]) -> list[dict]:
    """Finnhub returns bare ticker symbols; fill name + market cap so the peer
    table isn't half-blank. Both lookups degrade to None independently."""
    from ..providers.base import Peer
    return [
        Peer(ticker=t, name=_peer_name(t), market_cap=_peer_market_cap(t)).model_dump()
        for t in tickers
    ]


def _warning(section: str, code: str, message: str, *, provider: str | None = None) -> dict:
    out = {"section": section, "code": code, "message": message}
    if provider:
        out["provider"] = provider
    return out


def _provider_disabled(section: str, provider: str) -> dict:
    return _warning(
        section,
        "PROVIDER_DISABLED",
        f"{section.replace('_', ' ').title()} data is unavailable because the optional provider is not configured.",
        provider=provider,
    )


def _provider_error(section: str, provider: str) -> dict:
    return _warning(
        section,
        "PROVIDER_UNAVAILABLE",
        f"{section.replace('_', ' ').title()} data is temporarily unavailable from {provider}.",
        provider=provider,
    )


def _no_data(section: str) -> dict:
    return _warning(section, "NO_DATA", f"No {section.replace('_', ' ')} data is available for this ticker.")


def news(ticker: str) -> dict:
    warnings = []
    if not finnhub.enabled:
        warnings.append(_provider_disabled("news", "finnhub"))
        return {"articles": [], "available": False, "served_by": None, "warnings": warnings}
    try:
        articles = [a.model_dump() for a in finnhub.get_news(ticker)]
        if not articles:
            warnings.append(_no_data("news"))
        return {"articles": articles, "available": True, "served_by": "finnhub", "warnings": warnings}
    except Exception:
        log.warning("news provider failed", extra={"ticker": ticker, "provider": "finnhub"}, exc_info=True)
        warnings.append(_provider_error("news", "finnhub"))
        return {"articles": [], "available": True, "served_by": "finnhub", "warnings": warnings}


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
    # FMP (price targets) and Finnhub (recommendation buckets) are complementary.
    # Treat an upstream failure as a soft, server-logged event and only surface a
    # user-facing note if the section ends up with no usable data — otherwise a
    # premium-gated FMP endpoint produces a scary note even though Finnhub covered it.
    pending: list[dict] = []
    snap = None
    if fmp.enabled:
        try:
            snap = fmp.get_price_target(ticker)
        except Exception:
            log.warning("analyst price target provider failed", extra={"ticker": ticker, "provider": "fmp"}, exc_info=True)
            pending.append(_provider_error("analyst", "fmp"))
            snap = None
    else:
        pending.append(_provider_disabled("analyst", "fmp"))
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
            log.warning("analyst recommendation provider failed", extra={"ticker": ticker, "provider": "finnhub"}, exc_info=True)
            pending.append(_provider_error("analyst", "finnhub"))
    else:
        pending.append(_provider_disabled("analyst", "finnhub"))

    payload = None
    if snap is not None:
        snap.rating = _rating_label(snap)
        payload = snap.model_dump()
    has_data = payload is not None and any(
        payload.get(key) is not None
        for key in ("target_high", "target_low", "target_consensus", "target_median", "rating")
    )
    if has_data:
        # A source delivered usable data — drop upstream failure/disabled notes as noise.
        return {"analyst": payload, "available": True, "warnings": []}
    if not pending:
        pending.append(_no_data("analyst"))
    return {"analyst": payload, "available": bool(fmp.enabled or finnhub.enabled), "warnings": pending}


def peers(ticker: str) -> dict:
    # Prefer FMP peers (richer: name/price/market cap); fall back to Finnhub (free,
    # tickers only). A successful fallback drops the upstream note rather than leaving
    # a "temporarily unavailable from fmp" warning beside fully-populated peer data.
    pending: list[dict] = []
    if fmp.enabled:
        try:
            rows = fmp.get_peers(ticker)
            if rows:
                return {"peers": [p.model_dump() for p in rows], "served_by": "fmp", "warnings": []}
        except Exception:
            log.warning("peer provider failed", extra={"ticker": ticker, "provider": "fmp"}, exc_info=True)
            pending.append(_provider_error("peers", "fmp"))
    else:
        pending.append(_provider_disabled("peers", "fmp"))
    if finnhub.enabled:
        try:
            rows = _enrich_peers(finnhub.get_peers(ticker))
            if rows:
                return {"peers": rows, "served_by": "finnhub", "warnings": []}
        except Exception:
            log.warning("peer fallback provider failed", extra={"ticker": ticker, "provider": "finnhub"}, exc_info=True)
            pending.append(_provider_error("peers", "finnhub"))
    else:
        pending.append(_provider_disabled("peers", "finnhub"))
    pending.append(_no_data("peers"))
    return {"peers": [], "served_by": None, "warnings": pending}


def compare(tickers: list[str]) -> dict:
    """Key metrics for several tickers, side by side (reuses snapshot builder)."""
    out = []
    for t in tickers[:6]:
        try:
            out.append(screener.build_snapshot(t))
        except Exception as exc:
            out.append({"ticker": t.upper(), "error": str(exc)})
    return {"companies": out}
