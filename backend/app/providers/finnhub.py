"""Finnhub provider (PRD 02) — free tier: quote, company news, analyst
recommendation trends, peers. (Price targets are premium on Finnhub; we get
those from FMP instead.) Self-disables when no API key is configured.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..core.config import settings
from ..core.http import get_json
from ..core import cache
from .base import NewsArticle, Quote

_BASE = "https://finnhub.io/api/v1"


class FinnhubProvider:
    name = "finnhub"

    def __init__(self):
        self.key = settings.finnhub_api_key

    @property
    def enabled(self) -> bool:
        return bool(self.key)

    def _get(self, path: str, params: dict, ttl: int, key: str):
        def load():
            return get_json(f"{_BASE}/{path}", params={**params, "token": self.key}, provider=self.name)
        return cache.get_or_set("finnhub", key, ttl_seconds=ttl, loader=load).value

    def get_quote(self, ticker: str) -> Quote:
        d = self._get("quote", {"symbol": ticker.upper()}, ttl=120, key=f"quote:{ticker}")
        price, prev = d.get("c"), d.get("pc")
        return Quote(
            price=price, previous_close=prev,
            change_abs=d.get("d"), change_pct=(d.get("dp") / 100 if d.get("dp") is not None else None),
            currency="USD",
        )

    def get_news(self, ticker: str, *, days: int = 30) -> list[NewsArticle]:
        today = datetime.now(timezone.utc).date()
        params = {"symbol": ticker.upper(), "from": (today - timedelta(days=days)).isoformat(), "to": today.isoformat()}
        rows = self._get("company-news", params, ttl=3600, key=f"news:{ticker}:{days}")
        out = []
        for r in rows[:30]:
            ts = r.get("datetime")
            out.append(NewsArticle(
                headline=r.get("headline", "")[:300] or "(untitled)",
                summary=(r.get("summary") or None),
                source=r.get("source"),
                url=r.get("url", ""),
                published_at=(datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else None),
                image=(r.get("image") or None),
            ))
        return [a for a in out if a.url]

    def get_recommendation(self, ticker: str) -> dict:
        rows = self._get("stock/recommendation", {"symbol": ticker.upper()}, ttl=86400, key=f"rec:{ticker}")
        return rows[0] if rows else {}

    def get_peers(self, ticker: str) -> list[str]:
        rows = self._get("stock/peers", {"symbol": ticker.upper()}, ttl=7 * 86400, key=f"peers:{ticker}")
        return [t for t in rows if isinstance(t, str) and t.upper() != ticker.upper()][:12]
