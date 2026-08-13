"""Parent-side process boundary for memory-heavy screener data batches."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile

from ..core.errors import ProviderError
from .isolated_backtests import child_environment, process_failure


def _run(operation: str, payload: dict) -> dict:
    with tempfile.TemporaryDirectory(prefix="atlas-data-") as tmp:
        input_path = Path(tmp) / "input.json"
        output_path = Path(tmp) / "output.json"
        input_path.write_text(json.dumps(payload), encoding="utf-8")
        try:
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "app.jobs.data_batch_child",
                    "--operation",
                    operation,
                    "--input-json",
                    str(input_path),
                    "--output-json",
                    str(output_path),
                ],
                env=child_environment(),
                check=False,
            )
        except OSError as exc:
            raise ProviderError(f"Data worker could not start: {exc}") from exc
        if completed.returncode != 0:
            raise ProviderError(process_failure(completed.returncode, "Data worker"))
        if not output_path.exists():
            raise ProviderError("Data worker exited without a result")
        try:
            return json.loads(output_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ProviderError("Data worker returned an unreadable result") from exc


def ingest(tickers: list[str]) -> dict:
    return _run("screener-ingest", {"tickers": tickers})


def seed_universe(tickers: list[str] | None = None) -> dict:
    return _run("screener-seed", {"tickers": tickers})


def warm_universe(*, tickers: list[str] | None = None, include_default: bool = False) -> dict:
    return _run(
        "screener-warm",
        {"tickers": tickers, "include_default": include_default},
    )


def refresh_snapshots(*, include_default: bool = False) -> dict:
    return _run("snapshot-refresh", {"include_default": include_default})
