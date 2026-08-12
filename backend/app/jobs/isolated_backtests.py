"""Parent-side orchestration for memory-heavy disposable children."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile

from ..core.errors import ProviderError
from ..paper_trading import service
from ..paper_trading.schemas import BacktestRequest, ParameterSweepRequest


def child_environment() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    env.setdefault("MALLOC_ARENA_MAX", "2")
    env.setdefault("MALLOC_TRIM_THRESHOLD_", "65536")
    return env


def process_failure(returncode: int, worker: str = "Backtest worker") -> str:
    if returncode < 0:
        try:
            name = signal.Signals(-returncode).name
        except ValueError:
            name = f"signal {-returncode}"
        return f"{worker} was terminated by {name}"
    return f"{worker} exited with status {returncode}"


def _run_child_sync(run_id: int) -> int:
    completed = subprocess.run(
        [sys.executable, "-m", "app.jobs.backtest_child", "--run-id", str(run_id)],
        env=child_environment(),
        check=False,
    )
    return completed.returncode


def _completed_run(run_id: int) -> dict:
    run = service.get_backtest(run_id)["run"]
    if run["status"] != "completed":
        warning = (run.get("warnings") or ["Backtest did not complete"])[0]
        raise ProviderError(warning, run_id=run_id)
    return run


def _execute_running(run_id: int) -> dict:
    try:
        returncode = _run_child_sync(run_id)
    except OSError as exc:
        message = f"Backtest worker could not start: {exc}"
        service.fail_backtest(run_id, message)
        raise ProviderError(message, run_id=run_id) from exc
    if returncode != 0:
        message = process_failure(returncode)
        service.fail_backtest(run_id, message)
        if returncode < 0:
            raise ProviderError(message, run_id=run_id)
    return _completed_run(run_id)


def run_backtest(payload: BacktestRequest) -> dict:
    """Preserve the synchronous API contract while isolating its heavy heap."""
    run_id = int(service.start_backtest(payload)["run"]["id"])
    run = _execute_running(run_id)
    served_by = (run.get("inputs") or {}).get("served_by") or "derived"
    return {"run": run, "served_by": served_by, "holdings": run.get("holdings") or []}


def run_account_sleeve(
    strategy: dict,
    tickers: list[str],
    start_date: date,
    end_date: date,
    starting_cash: float,
) -> dict:
    """Return only the compact fields account aggregation needs from one child."""
    with tempfile.TemporaryDirectory(prefix="atlas-sleeve-") as tmp:
        input_path = Path(tmp) / "input.json"
        output_path = Path(tmp) / "output.json"
        input_path.write_text(json.dumps({
            "strategy": strategy,
            "tickers": tickers,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "starting_cash": starting_cash,
            "benchmark": "SPY",
        }), encoding="utf-8")
        try:
            completed = subprocess.run(
                [
                    sys.executable, "-m", "app.jobs.backtest_child",
                    "--input-json", str(input_path), "--output-json", str(output_path),
                ],
                env=child_environment(),
                check=False,
            )
        except OSError as exc:
            raise ProviderError(f"Backtest worker could not start: {exc}") from exc
        if completed.returncode != 0:
            raise ProviderError(process_failure(completed.returncode))
        if not output_path.exists():
            raise ProviderError("Backtest worker exited without an account result")
        return json.loads(output_path.read_text(encoding="utf-8"))


def run_parameter_sweep(payload: ParameterSweepRequest) -> dict:
    """Execute each sweep value in a fresh child, then rank compact stored results."""
    strategy_name, items = service.prepare_parameter_sweep(payload)
    rows = []
    for item in items:
        run_id = int(service.start_sweep_backtest(payload, item)["run"]["id"])
        run = _execute_running(run_id)
        rows.append({
            "run_id": run_id,
            "parameter": payload.parameter,
            "value": item["value"],
            "metrics": run.get("metrics") or {},
            "parameters": (run.get("strategy_snapshot") or {}).get("parameters") or {},
            "warnings": run.get("warnings") or [],
        })

    return service.assemble_parameter_sweep(payload, strategy_name, rows)


@dataclass(frozen=True)
class MaintenanceChildResult:
    returncode: int
    result: dict


def _run_maintenance_child_sync(
    phase: str,
    *,
    years: int,
    strategy_id: int | None = None,
    include_fundamentals: bool = True,
) -> MaintenanceChildResult:
    with tempfile.TemporaryDirectory(prefix="atlas-maint-") as tmp:
        output = Path(tmp) / "result.json"
        args = [
            sys.executable, "-m", "app.jobs.maintenance_cycle",
            "--phase", phase, "--reason", "manual-api",
            "--years", str(years), "--output-json", str(output),
        ]
        if strategy_id is not None:
            args.extend(("--strategy-id", str(strategy_id)))
        if not include_fundamentals:
            args.append("--skip-fundamentals")
        try:
            completed = subprocess.run(args, env=child_environment(), check=False)
        except OSError as exc:
            raise ProviderError(f"Maintenance worker could not start: {exc}") from exc
        result = json.loads(output.read_text(encoding="utf-8")) if output.exists() else {}
        return MaintenanceChildResult(completed.returncode, result)


def warm_backtest_data(*, years: int = 25, include_fundamentals: bool = True) -> dict:
    child = _run_maintenance_child_sync(
        "warm", years=years, include_fundamentals=include_fundamentals,
    )
    if child.returncode != 0:
        raise ProviderError(process_failure(child.returncode, "Maintenance worker"))
    return child.result.get("warmed") or {}


def refresh_headlines(*, years: int = 3) -> dict:
    targets = sorted(
        (int(row["id"]), str(row["name"]))
        for row in service.list_strategies()["strategies"]
    )
    refreshed = 0
    failed = []
    for strategy_id, name in targets:
        child = _run_maintenance_child_sync(
            "headline", years=years, strategy_id=strategy_id,
        )
        if child.returncode == 0:
            refreshed += 1
        else:
            failed.append({
                "strategy": name,
                "error": process_failure(child.returncode, "Maintenance worker"),
            })
    pruned = _run_maintenance_child_sync("prune", years=years)
    if pruned.returncode != 0:
        failed.append({
            "strategy": "retention prune",
            "error": process_failure(pruned.returncode, "Maintenance worker"),
        })
    end = date.today()
    start = end - timedelta(days=round(365.25 * years))
    return {
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "strategies": len(targets),
        "refreshed": refreshed,
        "failed": failed,
        "pruned_runs": (pruned.result.get("pruned_runs") if pruned.returncode == 0 else 0),
    }
