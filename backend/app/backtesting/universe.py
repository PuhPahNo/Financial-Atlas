"""Investable universe for active screening (PRD active-sp500-screening).

The S&P 500 constituents, fetched from a free CSV source and cached ~30 days, with a
bundled large-cap fallback used offline or if the fetch fails. We use *current*
membership (historical, survivorship-free membership is not freely available) and disclose
that as a caveat. Symbols are normalized to EDGAR/Yahoo hyphen form (BRK.B -> BRK-B).
"""
from __future__ import annotations

import csv
import io
import time
from datetime import date
from functools import lru_cache

from ..core import cache
from ..core.http import get_text

# Free, stable, keyless CSV of current S&P 500 constituents (Symbol in column 1).
_SP500_CSV = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"

# Free, keyless CSV of per-ticker S&P 500 membership stints (ticker,start_date,end_date;
# empty end = still a member; multiple rows per ticker for re-additions). This replaced
# the repo's old sp500_changes.csv, which upstream deleted — fetches 404'd and PIT
# membership silently degraded to today's list for a while. Interval data is also more
# robust than change-log reversal: membership is a direct date-range check.
_SP500_MEMBERSHIP_CSV = "https://raw.githubusercontent.com/fja05680/sp500/master/sp500_ticker_start_end.csv"

# Curated major ETFs / index funds (no EDGAR fundamentals → eligible for technical/rotation
# models, skipped by fundamental ones). Bundled and deterministic.
ETF_UNIVERSE = [
    # broad market
    "SPY", "VOO", "IVV", "VTI", "QQQ", "DIA", "IWM", "RSP", "MDY",
    # sectors (SPDR)
    "XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLU", "XLB", "XLRE", "XLC",
    # fixed income
    "AGG", "BND", "TLT", "IEF", "SHY", "LQD", "HYG", "TIP", "MUB",
    # commodities / real assets
    "GLD", "SLV", "DBC", "USO", "VNQ",
    # international
    "EFA", "EEM", "VEA", "VWO", "IEFA", "IEMG",
    # style / size / growth-value
    "VUG", "VTV", "IWF", "IWD", "IJH", "IJR",
    # thematic / leveraged-inverse used by some models
    "ARKK", "SQQQ", "TQQQ",
]

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


# --------------------------------------------------------------------------- #
# Point-in-time S&P 500 membership (PRD pit-membership)                         #
# --------------------------------------------------------------------------- #

def _norm(sym: str) -> str:
    return sym.strip().strip('"').upper().replace(".", "-")


def _to_iso(value: str) -> str | None:
    """Parse a date cell to ISO (YYYY-MM-DD). Tolerant of a few common formats."""
    v = value.strip().strip('"')
    if not v:
        return None
    if len(v) >= 10 and v[4] == "-" and v[7] == "-":
        return v[:10]
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            from datetime import datetime
            return datetime.strptime(v, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _parse_membership(text: str) -> list[dict]:
    """Parse the per-ticker stint CSV into [{ticker, start, end|None}] (header-aware)."""
    rows = [r for r in csv.reader(io.StringIO(text)) if any(c.strip() for c in r)]
    if not rows:
        return []
    header = [h.strip().lower() for h in rows[0]]

    def col(*keys):
        for i, h in enumerate(header):
            if any(k in h for k in keys):
                return i
        return None

    ti, si, ei = col("ticker", "symbol"), col("start"), col("end")
    if ti is None or si is None:
        return []
    out: list[dict] = []
    for cells in rows[1:]:
        if max(ti, si) >= len(cells):
            continue
        ticker = _norm(cells[ti])
        start = _to_iso(cells[si])
        end = _to_iso(cells[ei]) if (ei is not None and ei < len(cells) and cells[ei].strip()) else None
        if ticker and start:
            out.append({"ticker": ticker, "start": start, "end": end})
    return out


# Negative cache: after a membership-data failure, don't re-attempt the fetch on every
# members_on() call (a single backtest asks for hundreds of dates).
_membership_retry_at: float = 0.0


def _membership() -> list[dict] | None:
    """Per-ticker S&P 500 membership stints, cached ~30 days.

    Returns ``None`` when the data is unavailable (fetch failed / parsed empty) so
    callers can DISCLOSE the degradation instead of silently screening today's
    survivors under a point-in-time label."""
    global _membership_retry_at
    if time.monotonic() < _membership_retry_at:
        return None

    def load():
        text = get_text(_SP500_MEMBERSHIP_CSV, headers={"User-Agent": "Financial Atlas research tool"}, provider="universe")
        parsed = _parse_membership(text)
        if len(parsed) < 100:  # sanity floor — an error page or truncated body must not pass
            raise ValueError("S&P 500 membership CSV parsed too small")
        return parsed

    try:
        value = cache.get_or_set("universe", "sp500_membership", ttl_seconds=30 * 86400, loader=load).value
        if not value:
            # A previously-cached failure/empty parse must not pin degradation for the
            # whole TTL — refetch now and overwrite the cached entry.
            value = load()
            cache.put("universe", "sp500_membership", value)
    except Exception:  # noqa: BLE001
        _membership_retry_at = time.monotonic() + 300
        return None
    return value or None


def membership_available() -> bool:
    """True when point-in-time membership reconstruction is actually possible."""
    return _membership() is not None


@lru_cache(maxsize=4096)
def _members_on_iso(asof_iso: str) -> frozenset[str]:
    stints = _membership()
    if stints is None:
        # Degraded — NEVER memoize it: the next call should retry the source instead
        # of pinning survivorship bias for the process lifetime. (lru_cache does not
        # cache raising calls.)
        raise LookupError("sp500 membership data unavailable")
    return frozenset(
        s["ticker"] for s in stints
        if s["start"] <= asof_iso and (s["end"] is None or asof_iso <= s["end"])
    )


def members_on(asof) -> set[str]:
    """S&P 500 constituents as of a historical date (memoized). Falls back to the current
    membership when the stint data is unavailable — check ``membership_available()`` and
    disclose that degradation to the user."""
    asof_iso = asof.isoformat() if isinstance(asof, date) else str(asof)[:10]
    try:
        return set(_members_on_iso(asof_iso))
    except LookupError:
        return set(sp500_tickers())


def investable_superset() -> list[str]:
    """Every ticker the active engine may need to price: the current S&P 500, every name
    that was ever an index member per the stint data, and the bundled ETF universe."""
    names = {_norm(t) for t in sp500_tickers()}
    for stint in _membership() or []:
        names.add(stint["ticker"])
    names.update(_norm(t) for t in ETF_UNIVERSE)
    return sorted(names)
