"""Financial Modeling Prep provider (PRD 02) — new ``/stable/`` API.

Free tier: market-wide movers (gainers/losers/actives), company profile, TTM
ratios, analyst price-target consensus, and peers. Self-disables without a key.
"""
from __future__ import annotations

from ..core import cache, quota
from ..core.config import settings
from ..core.errors import ProviderError, RateLimitError
from ..core.http import get_json
from .base import AnalystSnapshot, Mover, Peer, Quote

_BASE = "https://financialmodelingprep.com/stable"
# Movers come back full of micro-cap pumps; require a price floor to surface
# meaningful names (FMP movers don't expose market cap to filter on).
_MIN_PRICE = 10.0


class FmpProvider:
    name = "fmp"

    def __init__(self):
        self.key = settings.fmp_api_key
        self.capabilities = frozenset()

    @property
    def enabled(self) -> bool:
        return bool(self.key)

    def _get(self, path: str, params: dict, ttl: int, key: str):
        def load():
            # Daily budget guard (PRD free-data-pipeline): only real network calls count
            # (cache hits never reach this loader). Past the budget we raise RateLimitError
            # so get_or_set serves stale data when it has any, and the provider chain
            # otherwise falls through to keyless sources — the key is never exhausted.
            if not quota.available(self.name, settings.fmp_daily_budget):
                raise RateLimitError(f"FMP daily budget ({settings.fmp_daily_budget}) reached")
            data = get_json(f"{_BASE}/{path}", params={**params, "apikey": self.key}, provider=self.name)
            quota.spend(self.name)
            return data
        return cache.get_or_set("fmp", key, ttl_seconds=ttl, loader=load).value

    def _movers(self, path: str, key: str) -> list[Mover]:
        rows = self._get(path, {}, ttl=900, key=key)
        out = []
        for r in rows if isinstance(rows, list) else []:
            price = r.get("price")
            if price is None or price < _MIN_PRICE:
                continue
            pct = r.get("changesPercentage")
            out.append(Mover(
                ticker=r.get("symbol"), name=r.get("name"), price=price,
                change=r.get("change"),
                change_pct=(pct / 100 if pct is not None else None),
            ))
        return out[:15]

    def gainers(self) -> list[Mover]:
        return self._movers("biggest-gainers", "gainers")

    def losers(self) -> list[Mover]:
        return self._movers("biggest-losers", "losers")

    def actives(self) -> list[Mover]:
        return self._movers("most-actives", "actives")

    def get_peers(self, ticker: str) -> list[Peer]:
        rows = self._get("stock-peers", {"symbol": ticker.upper()}, ttl=7 * 86400, key=f"peers:{ticker}")
        return [Peer(ticker=r.get("symbol"), name=r.get("companyName"), price=r.get("price"), market_cap=r.get("mktCap"))
                for r in (rows if isinstance(rows, list) else []) if r.get("symbol")][:12]

    def get_price_target(self, ticker: str) -> AnalystSnapshot:
        rows = self._get("price-target-consensus", {"symbol": ticker.upper()}, ttl=86400, key=f"pt:{ticker}")
        d = rows[0] if isinstance(rows, list) and rows else {}
        return AnalystSnapshot(
            target_high=d.get("targetHigh"), target_low=d.get("targetLow"),
            target_consensus=d.get("targetConsensus"), target_median=d.get("targetMedian"),
        )

    def get_quote(self, ticker: str) -> Quote:
        if not self.enabled:
            raise ProviderError("FMP key not configured")
        rows = self._get("quote", {"symbol": ticker.upper()}, ttl=60, key=f"quote:{ticker}")
        d = rows[0] if isinstance(rows, list) and rows else {}
        if not d:
            raise ProviderError(f"FMP no quote for {ticker}")
        price, prev = d.get("price"), d.get("previousClose")
        pct = d.get("changePercentage")
        return Quote(
            price=price, previous_close=prev,
            change_abs=d.get("change"),
            change_pct=(pct / 100 if pct is not None else None),
            week52_high=d.get("yearHigh"), week52_low=d.get("yearLow"),
            volume=int(d["volume"]) if d.get("volume") is not None else None,
            market_cap=d.get("marketCap"),
        )

    def get_ratios_ttm(self, ticker: str) -> dict:
        rows = self._get("ratios-ttm", {"symbol": ticker.upper()}, ttl=86400, key=f"ratios:{ticker}")
        return rows[0] if isinstance(rows, list) and rows else {}
