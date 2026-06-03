"""Snapshot refresh job (PRD 05 §6, PRD 30).

Recomputes the stored snapshot for every ticker in the local dataset (which
includes everything watchlisted or screened). Idempotent and resumable: one bad
ticker is logged and skipped. Runs locally via APScheduler or, in production, as
a Render Cron Job:  `python -m app.jobs.refresh`
"""
from __future__ import annotations

import logging

from ..db import CompanySnapshot, init_db, session_scope
from ..services import screener

log = logging.getLogger("jobs.refresh")


def run() -> dict:
    init_db()
    with session_scope() as s:
        tickers = [r[0] for r in s.query(CompanySnapshot.ticker).all()]

    refreshed, failed = 0, 0
    for ticker in tickers:
        try:
            screener.build_snapshot(ticker)
            refreshed += 1
        except Exception as exc:  # noqa: BLE001 - never let one ticker abort the run
            failed += 1
            log.warning("refresh failed for %s: %s", ticker, exc)

    result = {"tickers": len(tickers), "refreshed": refreshed, "failed": failed}
    log.info("refresh complete: %s", result)
    return result


if __name__ == "__main__":
    logging.basicConfig(level="INFO")
    print(run())
