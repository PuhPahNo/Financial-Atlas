"""Provider registry + fallback engine (PRD 02 §6).

Holds the instantiated providers and runs a capability's fallback chain: try
each capable provider in order, skipping ones that raise, and report which
provider served the result. EDGAR is authoritative for what it covers; the
keyed/keyless extras are convenience layers.
"""
from __future__ import annotations

from ..core.errors import NotFoundError, ProviderError, RateLimitError
from .finnhub import FinnhubProvider
from .fmp import FmpProvider
from .sec_edgar import SecEdgarProvider
from .yahoo import YahooProvider

sec_edgar = SecEdgarProvider()
yahoo = YahooProvider()
finnhub = FinnhubProvider()  # keyed; self-disables without FINNHUB_API_KEY
fmp = FmpProvider()          # keyed; self-disables without FMP_API_KEY

# Ordered fallback chains per logical domain (PRD 02 §6). Extend as keyed
# providers (FMP, Twelve Data, Finnhub) are registered.
CHAINS = {
    "profile": [sec_edgar],
    "income": [sec_edgar],
    "balance": [sec_edgar],
    "cashflow": [sec_edgar],
    "prices": [yahoo],
    "quote": [fmp, yahoo],  # FMP is fresher (~real-time) + has volume & market cap; Yahoo fallback
    "insider": [sec_edgar],
    "institutional": [sec_edgar],
    "filings": [sec_edgar],
}


def run_chain(domain: str, method: str, *args, **kwargs):
    """Call ``method`` on each provider in the domain chain until one succeeds.

    Returns ``(result, provider_name)``. Raises the last meaningful error if the
    whole chain fails.
    """
    providers = CHAINS.get(domain, [])
    last_exc: Exception | None = None
    for provider in providers:
        fn = getattr(provider, method, None)
        if fn is None:
            continue
        try:
            return fn(*args, **kwargs), provider.name
        except NotFoundError:
            raise  # ticker genuinely not found — no point trying fallbacks
        except (RateLimitError, ProviderError) as exc:
            last_exc = exc
            continue
    if last_exc:
        raise last_exc
    raise ProviderError(f"No provider available for domain '{domain}'")
