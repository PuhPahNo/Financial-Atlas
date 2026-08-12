"""Disposable worker for one bounded nightly-maintenance unit.

The Render web process launches this module as a child. The warm phase gets one
process; headline backtests get one process *per strategy*. Exiting after each unit
returns its heap to the OS instead of carrying allocator high-water memory into the
next model on the 512 MB web instance.
"""
from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
import resource
import sys

from ..core.heavy_work import lock as heavy_work_lock

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


def _run_warm() -> dict:
    # Import only after the cross-process lock is held. A child waiting behind an
    # interactive backtest should remain a tiny Python process, not preload the full
    # backtesting/provider graph while another heavy workload is resident.
    from . import warm_prices
    return warm_prices.run()


def _run_headline(strategy_id: int) -> dict:
    from . import refresh_headlines
    return refresh_headlines.run_one(strategy_id)


def _run_prune() -> int:
    from . import refresh_headlines
    return refresh_headlines.prune()


def run(reason: str, phase: str, *, strategy_id: int | None = None) -> dict:
    if phase == "headline" and strategy_id is None:
        raise ValueError("headline maintenance requires --strategy-id")
    if phase != "headline" and strategy_id is not None:
        raise ValueError("--strategy-id is valid only for the headline phase")

    prefer_child_for_oom_kill()
    result: dict = {"reason": reason, "phase": phase}
    log.info("maintenance child (%s/%s) started: peak_rss_mb=%s", reason, phase, _peak_rss_mb())
    with heavy_work_lock():
        if phase == "warm":
            result["warmed"] = _run_warm()
        elif phase == "headline":
            result["refreshed"] = _run_headline(strategy_id)
        elif phase == "prune":
            result["pruned_runs"] = _run_prune()
        else:  # Defensive for direct Python callers; argparse validates CLI calls.
            raise ValueError(f"unknown maintenance phase: {phase}")
        log.info(
            "maintenance child (%s/%s) complete: peak_rss_mb=%s",
            reason, phase, _peak_rss_mb(),
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reason", default="manual")
    parser.add_argument("--phase", choices=("warm", "headline", "prune"), required=True)
    parser.add_argument("--strategy-id", type=int)
    args = parser.parse_args()
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper())
    try:
        run(args.reason, args.phase, strategy_id=args.strategy_id)
        return 0
    except Exception:  # noqa: BLE001 — the parent records the failed child and remains healthy
        log.exception("maintenance child (%s/%s) failed", args.reason, args.phase)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
