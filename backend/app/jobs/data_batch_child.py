"""Disposable worker for user-triggered screener and snapshot batches."""
from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path

from ..core.heavy_work import lock as heavy_work_lock
from .maintenance_cycle import _peak_rss_mb, prefer_child_for_oom_kill
from .memory_guard import arm_cgroup_memory_guard

log = logging.getLogger("jobs.data_batch_child")


def execute(operation: str, payload: dict) -> dict:
    """Run one batch after the memory guard and global heavy-work lock are active."""
    prefer_child_for_oom_kill()
    arm_cgroup_memory_guard(f"data batch {operation}")
    log.info("data batch %s started: peak_rss_mb=%s", operation, _peak_rss_mb())
    with heavy_work_lock():
        from ..services import screener

        if operation == "screener-ingest":
            result = screener.ingest(payload.get("tickers") or [])
        elif operation == "screener-seed":
            result = screener.seed_universe(payload.get("tickers"))
        elif operation == "screener-warm":
            result = screener.warm_universe(
                tickers=payload.get("tickers"),
                include_default=bool(payload.get("include_default")),
            )
        elif operation == "snapshot-refresh":
            from . import refresh

            result = refresh.run(include_default=bool(payload.get("include_default")))
        else:
            raise ValueError(f"unknown data batch operation: {operation}")
        log.info("data batch %s complete: peak_rss_mb=%s", operation, _peak_rss_mb())
        return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--operation",
        choices=("screener-ingest", "screener-seed", "screener-warm", "snapshot-refresh"),
        required=True,
    )
    parser.add_argument("--input-json", required=True)
    parser.add_argument("--output-json", required=True)
    args = parser.parse_args()
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper())
    try:
        payload = json.loads(Path(args.input_json).read_text(encoding="utf-8"))
        result = execute(args.operation, payload)
        Path(args.output_json).write_text(json.dumps(result), encoding="utf-8")
        return 0
    except Exception:  # noqa: BLE001 — parent maps this to a bounded API error
        log.exception("data batch %s failed", args.operation)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
