"""Investable universe for active screening (PRD active-sp500-screening).

The S&P 500 constituents, fetched from a free CSV source and cached ~30 days, with a
bundled large-cap fallback used offline or if the fetch fails. We use *current*
membership (historical, survivorship-free membership is not freely available) and disclose
that as a caveat. Symbols are normalized to EDGAR/Yahoo hyphen form (BRK.B -> BRK-B).
"""
from __future__ import annotations

from ..core import cache
from ..core.http import get_text

# Free, stable, keyless CSV of current S&P 500 constituents (Symbol in column 1).
_SP500_CSV = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"

# Bundled large-cap fallback (used offline / on fetch failure). Not the full index, but a
# real multi-sector universe so screening is meaningful without network access.
_FALLBACK = [
    "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "META", "NVDA", "TSLA", "BRK-B", "AVGO",
    "JPM", "V", "MA", "UNH", "HD", "COST", "LLY", "XOM", "JNJ", "PG", "ABBV", "MRK",
    "ADBE", "CRM", "NFLX", "AMD", "KO", "PEP", "WMT", "BAC", "WFC", "GS", "MS", "C",
    "CVX", "COP", "INTC", "QCOM", "TXN", "ORCL", "IBM", "CSCO", "ACN", "NOW", "INTU",
    "PFE", "TMO", "ABT", "DHR", "BMY", "AMGN", "GILD", "CVS", "MDT", "ISRG", "SYK",
    "DIS", "CMCSA", "T", "VZ", "TMUS", "NKE", "MCD", "SBUX", "LOW", "TJX", "BKNG",
    "CAT", "DE", "BA", "HON", "GE", "LMT", "RTX", "UPS", "UNP", "MMM", "EMR",
    "PM", "MO", "MDLZ", "CL", "KMB", "GIS", "F", "GM", "PYPL", "AXP", "BLK", "SCHW",
    "SPGI", "ICE", "CME", "PLD", "AMT", "EQIX", "LIN", "APD", "SHW", "FCX", "NEM",
    "DUK", "SO", "NEE", "D", "AEP", "EOG", "SLB", "MPC", "PSX", "VLO", "OXY", "WMB",
    "ADP", "BDX", "VRTX", "REGN", "ZTS", "CB", "PGR", "MMC", "AON", "ELV", "CI", "HUM",
]


def _parse_csv(text: str) -> list[str]:
    out: list[str] = []
    for i, line in enumerate(text.splitlines()):
        if i == 0 or not line.strip():  # skip header / blanks
            continue
        sym = line.split(",", 1)[0].strip().strip('"').upper()
        if sym:
            out.append(sym.replace(".", "-"))
    return out


def sp500_tickers() -> list[str]:
    """Current S&P 500 tickers (cached ~30 days). Falls back to the bundled list."""
    def load():
        text = get_text(_SP500_CSV, headers={"User-Agent": "Financial Atlas research tool"}, provider="universe")
        parsed = _parse_csv(text)
        return parsed if len(parsed) >= 100 else _FALLBACK  # sanity floor

    try:
        value = cache.get_or_set("universe", "sp500_constituents", ttl_seconds=30 * 86400, loader=load).value
    except Exception:  # noqa: BLE001 — never let universe sourcing break a backtest
        return list(_FALLBACK)
    return list(value) if value else list(_FALLBACK)
