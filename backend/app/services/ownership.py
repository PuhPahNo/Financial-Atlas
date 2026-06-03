"""Ownership service (PRD 16, 17) — insider transactions + large stakes.

Insider data comes from parsed SEC Form 4 filings; large/activist stakes from
13D/13G filings in the company's own submissions. Full 13F holder-by-holder
reconstruction is a documented future enhancement (it requires reverse-indexing
every institution's 13F by CUSIP — heavy and unreliable on free tiers).
"""
from __future__ import annotations

from datetime import date, timedelta

from ..providers.registry import run_chain

_CLUSTER_DAYS = 30
_CLUSTER_MIN_INSIDERS = 3


def insiders(ticker: str) -> dict:
    txns, served_by = run_chain("insider", "get_insider_transactions", ticker)
    rows = [t.model_dump() for t in txns]

    cutoff_30 = (date.today() - timedelta(days=30)).isoformat()
    cutoff_90 = (date.today() - timedelta(days=90)).isoformat()

    def net(cutoff: str) -> float:
        total = 0.0
        for t in txns:
            if not t.is_open_market or not t.value or not t.transaction_date or t.transaction_date < cutoff:
                continue
            total += t.value if t.acquired_disposed == "A" else -t.value
        return total

    buyers = {t.insider_name for t in txns
              if t.is_open_market and t.acquired_disposed == "A"
              and t.transaction_date and t.transaction_date >= cutoff_90}
    cluster_buy = len(buyers) >= _CLUSTER_MIN_INSIDERS

    summary = {
        "net_value_30d": net(cutoff_30),
        "net_value_90d": net(cutoff_90),
        "buy_count": sum(1 for t in txns if t.transaction_code == "P"),
        "sell_count": sum(1 for t in txns if t.transaction_code == "S"),
        "cluster_buy": cluster_buy,
    }
    return {"transactions": rows, "summary": summary, "served_by": served_by}


def institutions(ticker: str) -> dict:
    """Large/activist stakes from 13D/13G (free & reliable)."""
    stakes, served_by = run_chain("institutional", "get_large_stakes", ticker)
    return {
        "large_stakes": [s.model_dump() for s in stakes],
        "note": "Large stakes from 13D/13G filings. Full 13F holder-level breakdown is a planned enhancement.",
        "served_by": served_by,
    }
