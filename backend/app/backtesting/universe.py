"""Investable universe for active screening (PRD active-sp500-screening).

The S&P 500 constituents, fetched from a free CSV source and cached ~30 days, with a
bundled large-cap fallback used offline or if the fetch fails. We use *current*
membership (historical, survivorship-free membership is not freely available) and disclose
that as a caveat. Symbols are normalized to EDGAR/Yahoo hyphen form (BRK.B -> BRK-B).
"""
from __future__ import annotations

import csv
import io
from datetime import date
from functools import lru_cache

from ..core import cache
from ..core.http import get_text

# Free, stable, keyless CSV of current S&P 500 constituents (Symbol in column 1).
_SP500_CSV = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"

# Free, keyless CSV of S&P 500 add/remove changes (date, added, removed). Best-effort:
# if unreachable, membership reconstruction degrades to the current list (no regression).
_SP500_CHANGES_CSV = "https://raw.githubusercontent.com/fja05680/sp500/master/sp500_changes.csv"

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


def _parse_changes(text: str) -> list[dict]:
    """Parse a change-log CSV into [{date, added, removed}] (best-effort, header-aware).
    Uses a real CSV reader so quoted date cells like "March 2, 2020" parse correctly."""
    rows = [r for r in csv.reader(io.StringIO(text)) if any(c.strip() for c in r)]
    if not rows:
        return []
    header = [h.strip().lower() for h in rows[0]]

    def col(*keys):
        for i, h in enumerate(header):
            if any(k in h for k in keys):
                return i
        return None

    di, ai, ri = col("date"), col("added", "add"), col("removed", "remove")
    if di is None or (ai is None and ri is None):
        return []
    out: list[dict] = []
    for cells in rows[1:]:
        if di >= len(cells):
            continue
        iso = _to_iso(cells[di])
        if not iso:
            continue
        added = _norm(cells[ai]) if (ai is not None and ai < len(cells) and cells[ai].strip()) else ""
        removed = _norm(cells[ri]) if (ri is not None and ri < len(cells) and cells[ri].strip()) else ""
        if added or removed:
            out.append({"date": iso, "added": added, "removed": removed})
    return out


def _changes() -> list[dict]:
    """S&P 500 add/remove change-log, cached ~30 days. Returns [] on any failure, in which
    case membership reconstruction degrades to the current list (no regression)."""
    def load():
        text = get_text(_SP500_CHANGES_CSV, headers={"User-Agent": "Financial Atlas research tool"}, provider="universe")
        return _parse_changes(text)

    try:
        value = cache.get_or_set("universe", "sp500_changes", ttl_seconds=30 * 86400, loader=load).value
    except Exception:  # noqa: BLE001
        return []
    return value or []


def reconstruct(current: set[str], changes: list[dict], asof) -> set[str]:
    """Membership as of ``asof``: start from the current set and reverse every change dated
    *after* asof (newest→oldest: drop the ticker that was added, restore the one removed)."""
    asof_iso = asof.isoformat() if isinstance(asof, date) else str(asof)[:10]
    members = {_norm(t) for t in current}
    for ch in sorted(changes, key=lambda c: c["date"], reverse=True):
        if ch["date"] <= asof_iso:
            break
        if ch.get("added"):
            members.discard(ch["added"])
        if ch.get("removed"):
            members.add(ch["removed"])
    return members


@lru_cache(maxsize=4096)
def _members_on_iso(asof_iso: str) -> frozenset[str]:
    return frozenset(reconstruct(set(sp500_tickers()), _changes(), asof_iso))


def members_on(asof) -> set[str]:
    """S&P 500 constituents as of a historical date (memoized). Falls back to the current
    membership when the change-log is unavailable."""
    asof_iso = asof.isoformat() if isinstance(asof, date) else str(asof)[:10]
    return set(_members_on_iso(asof_iso))


def investable_superset() -> list[str]:
    """Every ticker the active engine may need to price: the current S&P 500, every name
    ever added/removed in the change-log, and the bundled ETF universe."""
    names = {_norm(t) for t in sp500_tickers()}
    for ch in _changes():
        if ch.get("added"):
            names.add(ch["added"])
        if ch.get("removed"):
            names.add(ch["removed"])
    names.update(_norm(t) for t in ETF_UNIVERSE)
    return sorted(names)
