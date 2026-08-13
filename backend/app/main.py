"""FastAPI application entrypoint (PRD 01, 04)."""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api import assistant, backtesting, paper_trading
from .api.routes import router
from .core import market_hours
from .core.config import settings
from .core.errors import AtlasError
from .db import init_db
from .jobs import isolated_backtests
from .jobs.memory_guard import MEMORY_GUARD_EXIT_CODE
from .paper_trading import accounts, service as pt_service

logging.basicConfig(level=settings.log_level.upper())
for noisy_logger in ("httpx", "httpcore"):
    logging.getLogger(noisy_logger).setLevel(logging.WARNING)

log = logging.getLogger("app.live_mark")


async def _live_mark_loop() -> None:
    """Pre-warm account live marks on an interval while the US market is open.

    Runs in-process inside the single web service (no extra Render service/cron). Sleeps
    first so boot isn't a burst; only touches the network during market hours; and never
    lets a single failure kill the loop. Correctness does not depend on this — the read
    path re-marks on demand — so a paused/sleeping instance self-heals on the next request.
    """
    interval = max(15, settings.live_mark_interval_seconds)
    while True:
        try:
            await asyncio.sleep(interval)
            if market_hours.is_market_open():
                refreshed = await asyncio.to_thread(accounts.warm_active_marks)
                if refreshed:
                    log.debug("live-mark tick refreshed %d account(s)", refreshed)
        except asyncio.CancelledError:
            break
        except Exception as exc:  # noqa: BLE001 — keep the loop alive across transient errors
            log.warning("live-mark tick error: %s", exc)


async def _backtest_worker_loop() -> None:
    """Single queue coordinator for disposable backtest child processes.

    One job at a time; each claimed run gets a fresh interpreter so full-universe
    arrays and allocator arenas are returned to the OS on exit. A restart marks
    interrupted jobs failed instead of leaving them 'running' forever.
    """
    worker_log = logging.getLogger("app.backtest_worker")
    try:
        stale = await asyncio.to_thread(pt_service.fail_interrupted_backtests)
        if stale:
            worker_log.warning("marked %d interrupted backtest job(s) failed on boot", stale)
    except Exception as exc:  # noqa: BLE001
        worker_log.warning("boot sweep error: %s", exc)
    while True:
        try:
            run_id = await asyncio.to_thread(pt_service.claim_next_queued_backtest)
            if run_id is None:
                await asyncio.sleep(2)
                continue
            worker_log.info("executing queued backtest run %d", run_id)
            await _run_backtest_child(run_id)
        except asyncio.CancelledError:
            break
        except Exception as exc:  # noqa: BLE001 — keep the worker alive
            log.warning("backtest worker error: %s", exc)
            await asyncio.sleep(2)


async def _run_backtest_child(run_id: int) -> bool:
    """Execute one claimed run in a fresh interpreter and settle process failures."""
    worker_log = logging.getLogger("app.backtest_worker")
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "app.jobs.backtest_child",
            "--run-id",
            str(run_id),
            env=isolated_backtests.child_environment(),
        )
    except OSError as exc:
        message = f"Backtest worker could not start: {exc}"
        pt_service.fail_backtest(run_id, message)
        worker_log.error("queued backtest run %d failed: %s", run_id, message)
        return False
    try:
        returncode = await proc.wait()
    except asyncio.CancelledError:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=10)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
        pt_service.fail_backtest(run_id, "Backtest interrupted by service shutdown")
        raise

    if returncode == 0:
        worker_log.info("queued backtest run %d child complete", run_id)
        return True
    message = isolated_backtests.process_failure(returncode)
    pt_service.fail_backtest(run_id, message)
    worker_log.error("queued backtest run %d failed: %s", run_id, message)
    return False


async def _data_maintenance_loop() -> None:
    """Nightly free-data maintenance on the existing single web service.

    Warms the durable price store + PIT fundamentals for the investable superset, then
    refreshes every model card's headline backtest so stored numbers always come from
    the current engine. Also runs once shortly after boot when the price store is cold
    (fresh deploy / wiped DB) — production primes itself with no manual steps. Same
    resilience contract as the live-mark loop: nothing here can kill the loop, and
    correctness never depends on it (on-demand paths self-heal).
    """
    maint_log = logging.getLogger("app.data_maintenance")

    def needs_bootstrap() -> bool:
        """Cold price store (fresh deploy / wiped DB) — or no seeded model carries a
        recent headline (an interrupted bootstrap, or an engine change since the last
        refresh). Once one full refresh lands, redeploys skip this and the nightly
        run takes over."""
        from .db import PriceSeries, session_scope
        from .models.paper_trading import TradingStrategy
        with session_scope() as s:
            if s.query(PriceSeries).count() < 50:
                return True
            cutoff = (datetime.now(timezone.utc) - timedelta(days=2)).date().isoformat()
            for row in s.query(TradingStrategy).filter_by(status="active", origin="seeded").all():
                window = ((row.metrics_json or {}).get("_backtest") or {}).get("window") or {}
                if (window.get("end") or "") >= cutoff:
                    return False
            return True

    await asyncio.sleep(120)  # let boot settle before any heavy work
    try:
        if needs_bootstrap():
            await _run_data_maintenance_process("bootstrap")
    except Exception as exc:  # noqa: BLE001
        maint_log.warning("data maintenance bootstrap error: %s", exc)

    while True:
        try:
            now = datetime.now(timezone.utc)
            target = now.replace(hour=settings.data_maintenance_utc_hour, minute=30,
                                 second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
            await asyncio.sleep((target - now).total_seconds())
            await _run_data_maintenance_process("nightly")
        except asyncio.CancelledError:
            break
        except Exception as exc:  # noqa: BLE001 — keep the loop alive across transient errors
            maint_log.warning("data maintenance error: %s", exc)


def _headline_refresh_targets() -> list[tuple[int, str]]:
    """Small parent-process query used to plan one child per active strategy."""
    from .paper_trading import service as pt_service
    rows = pt_service.list_strategies()["strategies"]
    return sorted((int(row["id"]), str(row["name"])) for row in rows)


async def _run_maintenance_child(
    reason: str,
    phase: str,
    env: dict[str, str],
    *,
    strategy_id: int | None = None,
    strategy_name: str | None = None,
) -> bool:
    """Run one bounded maintenance unit and keep failures local to that unit."""
    maint_log = logging.getLogger("app.data_maintenance")
    label = phase if strategy_id is None else f"headline:{strategy_id}:{strategy_name or 'unknown'}"
    args = [
        sys.executable, "-m", "app.jobs.maintenance_cycle",
        "--phase", phase, "--reason", reason,
    ]
    if strategy_id is not None:
        args.extend(("--strategy-id", str(strategy_id)))

    maint_log.info("data maintenance (%s/%s): launching isolated child", reason, label)
    proc = await asyncio.create_subprocess_exec(*args, env=env)
    try:
        returncode = await proc.wait()
    except asyncio.CancelledError:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=10)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
        raise

    if returncode == 0:
        maint_log.info("data maintenance (%s/%s): child complete", reason, label)
        return True
    if returncode == MEMORY_GUARD_EXIT_CODE:
        maint_log.error(
            "data maintenance (%s/%s): memory guard stopped child; continuing sweep",
            reason, label,
        )
        return False
    if returncode < 0:
        try:
            signal_name = signal.Signals(-returncode).name
        except ValueError:
            signal_name = f"signal {-returncode}"
        maint_log.error(
            "data maintenance (%s/%s): child terminated by %s; continuing sweep",
            reason, label, signal_name,
        )
    else:
        maint_log.error(
            "data maintenance (%s/%s): child exited %d; continuing sweep",
            reason, label, returncode,
        )
    return False


async def _run_data_maintenance_process(reason: str) -> bool:
    """Warm once, then refresh each headline in a fresh same-instance child.

    A per-strategy process boundary releases each heap before the next strategy.
    Universe-window bounds reduce the individual peak, while the child memory guard
    preserves the API if a future strategy still cannot fit this Render plan.
    """
    maint_log = logging.getLogger("app.data_maintenance")
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    env.setdefault("MALLOC_ARENA_MAX", "2")
    env.setdefault("MALLOC_TRIM_THRESHOLD_", "65536")

    all_ok = await _run_maintenance_child(reason, "warm", env)
    try:
        targets = await asyncio.to_thread(_headline_refresh_targets)
    except Exception as exc:  # noqa: BLE001 — keep the API alive if planning fails
        maint_log.error("data maintenance (%s/headlines): target query failed: %s", reason, exc)
        return False

    maint_log.info("data maintenance (%s/headlines): refreshing %d strategies", reason, len(targets))
    for strategy_id, strategy_name in targets:
        completed = await _run_maintenance_child(
            reason,
            "headline",
            env,
            strategy_id=strategy_id,
            strategy_name=strategy_name,
        )
        all_ok = completed and all_ok

    pruned = await _run_maintenance_child(reason, "prune", env)
    return pruned and all_ok


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()  # idempotent; ensures tables exist when started via uvicorn lifespan
    tasks = [asyncio.create_task(_backtest_worker_loop())]
    if settings.live_mark_enabled:
        tasks.append(asyncio.create_task(_live_mark_loop()))
    if settings.data_maintenance_enabled:
        tasks.append(asyncio.create_task(_data_maintenance_loop()))
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass


app = FastAPI(title="Financial Atlas API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

@app.middleware("http")
async def security_headers(request: Request, call_next):
    # Next.js applies its next.config hardening headers to pages but not to
    # responses proxied through the /api rewrite, so the backend sets its own.
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Content-Security-Policy", "frame-ancestors 'none'")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return response


app.include_router(router)
app.include_router(assistant.router)
app.include_router(paper_trading.router)
app.include_router(backtesting.router)


@app.exception_handler(AtlasError)
async def atlas_error_handler(_: Request, exc: AtlasError):
    body = {"error": {"code": exc.code, "message": exc.message, **exc.context}}
    return JSONResponse(status_code=exc.http_status, content=body)


@app.get("/health")
def health():
    # Minimal on purpose: this is a liveness probe, not an info endpoint.
    return {"status": "ok"}
