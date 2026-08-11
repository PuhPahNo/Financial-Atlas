"""Disposable worker for the single-service nightly maintenance phases.

The Render web process launches this module as a child. Heap accumulated while
warming or backtesting is returned to the OS when each phase exits, and an OOM can
preferentially kill this worker without taking the API down.
"""
from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
import resource
import sys

from ..core.heavy_work import lock as heavy_work_lock
from . import refresh_headlines, warm_prices

log = logging.getLogger("jobs.maintenance_cycle")


def prefer_child_for_oom_kill() -> None:
    """Best-effort: make this disposable child a better Linux OOM victim."""
    try:
        Path("/proc/self/oom_score_adj").write_text("500", encoding="ascii")
    except OSError:
        pass


def _peak_rss_mb() -> float:
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    divisor = 1024 * 1024 if sys.platform == "darwin" else 1024
    return round(usage / divisor, 1)


def run(reason: str, phase: str = "all") -> dict:
    prefer_child_for_oom_kill()
    result: dict = {"reason": reason, "phase": phase}
    log.info("maintenance child (%s/%s) started: peak_rss_mb=%s", reason, phase, _peak_rss_mb())
    with heavy_work_lock():
        if phase in {"warm", "all"}:
            result["warmed"] = warm_prices.run()
            log.info("maintenance child (%s/warm) complete: peak_rss_mb=%s", reason, _peak_rss_mb())
        if phase in {"headlines", "all"}:
            result["refreshed"] = refresh_headlines.run()
            log.info(
                "maintenance child (%s/headlines) complete: peak_rss_mb=%s",
                reason, _peak_rss_mb(),
            )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reason", default="manual")
    parser.add_argument("--phase", choices=("warm", "headlines", "all"), default="all")
    args = parser.parse_args()
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper())
    try:
        run(args.reason, args.phase)
        return 0
    except Exception:  # noqa: BLE001 — the parent records the failed child and remains healthy
        log.exception("maintenance child (%s/%s) failed", args.reason, args.phase)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
