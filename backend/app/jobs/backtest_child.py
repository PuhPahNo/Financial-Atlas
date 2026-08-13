"""Disposable child for one database-backed backtest run."""
from __future__ import annotations

import argparse
from datetime import date
import json
import logging
import os
from pathlib import Path

from ..core.heavy_work import lock as heavy_work_lock
from .maintenance_cycle import _peak_rss_mb, prefer_child_for_oom_kill
from .memory_guard import arm_cgroup_memory_guard

log = logging.getLogger("jobs.backtest_child")


def run(run_id: int) -> bool:
    """Execute exactly one running job, returning all allocated heap on exit."""
    prefer_child_for_oom_kill()
    arm_cgroup_memory_guard(f"backtest {run_id}")
    log.info("backtest child %d started: peak_rss_mb=%s", run_id, _peak_rss_mb())
    # Acquire before importing the service/engine graph so a waiting child remains
    # tiny while maintenance or another backtest owns the instance's memory budget.
    with heavy_work_lock():
        from ..paper_trading import service

        completed = service.execute_queued_backtest(run_id)
        log.info(
            "backtest child %d %s: peak_rss_mb=%s",
            run_id,
            "complete" if completed else "failed",
            _peak_rss_mb(),
        )
        return completed


def run_ephemeral(input_json: str, output_json: str) -> bool:
    """Execute an account sleeve without adding a user-visible BacktestRun row."""
    prefer_child_for_oom_kill()
    arm_cgroup_memory_guard("ephemeral account sleeve")
    with heavy_work_lock():
        from ..paper_trading import service

        payload = json.loads(Path(input_json).read_text(encoding="utf-8"))
        payload["start_date"] = date.fromisoformat(payload["start_date"])
        payload["end_date"] = date.fromisoformat(payload["end_date"])
        result = service.execute_backtest(**payload)
        compact = {
            key: result.get(key)
            for key in (
                "equity_curve", "trades", "warnings", "residual_cash", "final_holdings",
            )
        }
        Path(output_json).write_text(
            json.dumps(compact, default=lambda value: value.isoformat() if isinstance(value, date) else str(value)),
            encoding="utf-8",
        )
        log.info("ephemeral account sleeve complete: peak_rss_mb=%s", _peak_rss_mb())
        return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--run-id", type=int)
    mode.add_argument("--input-json")
    parser.add_argument("--output-json")
    args = parser.parse_args()
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper())
    try:
        if args.run_id is not None:
            return 0 if run(args.run_id) else 1
        if not args.output_json:
            parser.error("--output-json is required with --input-json")
        return 0 if run_ephemeral(args.input_json, args.output_json) else 1
    except Exception:  # noqa: BLE001 — parent converts child failure into job state
        log.exception("backtest child crashed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
