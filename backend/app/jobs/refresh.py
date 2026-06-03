"""Snapshot refresh job (PRD 05 §6, PRD 30).

Recomputes the stored snapshot for every ticker in the local dataset (which
includes everything watchlisted or screened). Idempotent and resumable: one bad
ticker is logged and skipped. Runs locally via APScheduler or, in production, as
a Render Cron Job:  `python -m app.jobs.refresh`
"""
from __future__ import annotations

import logging

from ..db import init_db
from ..services import screener

log = logging.getLogger("jobs.refresh")


def run(*, include_default: bool = False) -> dict:
    init_db()
    tickers = screener.tracked_tickers(include_default=include_default)

    refreshed, failed, skipped = 0, 0, 0
    details = []
    for ticker in tickers:
        detail = screener.warm_ticker(ticker)
        details.append(detail)
        if detail["status"] == "ok":
            refreshed += 1
        elif detail["domains"]:
            failed += 1
            log.warning("refresh failed for %s: %s", ticker, detail["domains"])
        else:
            skipped += 1

    result = {
        "tickers": len(tickers),
        "refreshed": refreshed,
        "failed": failed,
        "skipped": skipped,
        "details": details,
    }
    log.info("refresh complete: %s", result)
    return result


if __name__ == "__main__":
    logging.basicConfig(level="INFO")
    print(run())
