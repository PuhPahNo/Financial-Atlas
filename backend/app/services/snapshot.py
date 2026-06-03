"""Composed company snapshot service for fast overview screens."""
from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from ..core import cache as cache_service
from ..providers.base import Period
from ..valuation import service as valuation_service
from . import company, financials, prices, research

logger = logging.getLogger(__name__)


def _section(
    available: bool,
    served_by: str | None = None,
    stale: bool = False,
    cache: dict[str, Any] | None = None,
    warnings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    cache = cache or _cache_summary([])
    return {
        "available": available,
        "served_by": served_by,
        "stale": stale or cache["stale"],
        "cache": cache,
        "warnings": warnings or [],
    }


def _iso(timestamp: float | None) -> str | None:
    if timestamp is None:
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def _cache_summary(events: list[cache_service.CacheEvent]) -> dict[str, Any]:
    statuses = [event.status for event in events]
    stored = [event.stored_at for event in events if event.stored_at is not None]
    ages = [event.age_seconds for event in events if event.age_seconds is not None]
    stale = any(event.stale for event in events)
    if stale:
        status = "stale"
    elif "miss" in statuses:
        status = "miss"
    elif "bypass" in statuses:
        status = "bypass"
    elif "hit" in statuses:
        status = "hit"
    else:
        status = "not_used"
    return {
        "status": status,
        "hit_count": statuses.count("hit"),
        "miss_count": statuses.count("miss"),
        "stale_count": statuses.count("stale"),
        "bypass_count": statuses.count("bypass"),
        "stale": stale,
        "as_of": _iso(max(stored) if stored else None),
        "max_age_seconds": max(ages) if ages else None,
    }


def _warning(section: str) -> dict[str, str]:
    return {
        "section": section,
        "code": "SECTION_UNAVAILABLE",
        "message": f"{section.replace('_', ' ')} data is unavailable right now.",
    }


def _extend_warnings(warnings: list[dict[str, Any]], section_data: Any) -> list[dict[str, Any]]:
    section_warnings = section_data.get("warnings", []) if isinstance(section_data, dict) else []
    warnings.extend(section_warnings)
    return section_warnings


def _optional(
    ticker: str,
    section: str,
    warnings: list[dict[str, str]],
    loader: Callable[[], Any],
) -> tuple[Any | None, dict[str, Any]]:
    error: Exception | None = None
    with cache_service.trace_events() as events:
        value: Any | None = None
        try:
            value = loader()
        except Exception as exc:
            error = exc
    cache = _cache_summary(events)
    if error is not None:
        logger.warning(
            "Snapshot section unavailable",
            extra={"ticker": ticker, "section": section},
            exc_info=(type(error), error, error.__traceback__),
        )
        warnings.append(_warning(section))
        return None, cache
    return value, cache


def overview_snapshot(
    ticker: str,
    *,
    period: Period = Period.ANNUAL,
    price_range: str = "1y",
    interval: str = "1d",
) -> dict[str, Any]:
    """Return all overview sections through one service call.

    The company overview is required because it powers the page identity and metric grid. Optional
    sections degrade independently so provider/key gaps do not blank the whole overview.
    """
    symbol = ticker.upper()
    warnings: list[dict[str, str]] = []

    with cache_service.trace_events() as company_events:
        company_data = company.overview(symbol)
    company_cache = _cache_summary(company_events)
    sections: dict[str, dict[str, Any]] = {
        "company": _section(True, company_data.get("served_by"), cache=company_cache),
    }

    valuation_data, valuation_cache = _optional(symbol, "valuation", warnings, lambda: valuation_service.valuate(symbol))
    sections["valuation"] = _section(
        valuation_data is not None,
        "derived" if valuation_data is not None else None,
        cache=valuation_cache,
    )

    cash_flow_result, cash_flow_cache = _optional(
        symbol,
        "cash_flow_analysis",
        warnings,
        lambda: financials.cash_flow_analysis(symbol, period),
    )
    cash_flow_data = (
        {
            "periods": cash_flow_result.get("periods", []),
            "scorecard": cash_flow_result.get("scorecard"),
            "currency": "USD",
        }
        if cash_flow_result is not None else None
    )
    sections["cash_flow_analysis"] = _section(
        cash_flow_result is not None,
        cash_flow_result.get("served_by") if cash_flow_result is not None else None,
        cache=cash_flow_cache,
    )

    analyst_data, analyst_cache = _optional(symbol, "analyst", warnings, lambda: research.analyst(symbol))
    sections["analyst"] = _section(
        bool(analyst_data.get("available")) if analyst_data is not None else False,
        analyst_data.get("served_by") if isinstance(analyst_data, dict) else None,
        cache=analyst_cache,
        warnings=_extend_warnings(warnings, analyst_data),
    )

    news_data, news_cache = _optional(symbol, "news", warnings, lambda: research.news(symbol))
    sections["news"] = _section(
        bool(news_data.get("available")) if news_data is not None else False,
        news_data.get("served_by") if isinstance(news_data, dict) else None,
        cache=news_cache,
        warnings=_extend_warnings(warnings, news_data),
    )

    peers_data, peers_cache = _optional(symbol, "peers", warnings, lambda: research.peers(symbol))
    sections["peers"] = _section(
        bool(peers_data.get("peers")) if isinstance(peers_data, dict) else False,
        peers_data.get("served_by") if isinstance(peers_data, dict) else None,
        cache=peers_cache,
        warnings=_extend_warnings(warnings, peers_data),
    )

    price_result, price_cache = _optional(
        symbol,
        "prices",
        warnings,
        lambda: prices.price_history(symbol, range=price_range, interval=interval),
    )
    if price_result is not None:
        price_data, price_served_by = price_result
    else:
        price_data, price_served_by = None, None
    sections["prices"] = _section(price_data is not None, price_served_by, cache=price_cache)

    as_of_values = [
        section.get("cache", {}).get("as_of")
        for section in sections.values()
        if section.get("cache", {}).get("as_of") is not None
    ]

    return {
        "ticker": symbol,
        "company": company_data,
        "valuation": valuation_data,
        "cash_flow_analysis": cash_flow_data,
        "analyst": analyst_data,
        "news": news_data,
        "peers": peers_data,
        "prices": price_data,
        "sections": sections,
        "warnings": warnings,
        "as_of": max(as_of_values) if as_of_values else None,
    }
