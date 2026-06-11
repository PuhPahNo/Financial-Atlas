"""FastAPI application entrypoint (PRD 01, 04)."""
from __future__ import annotations

import asyncio
import logging
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
from .paper_trading import accounts

logging.basicConfig(level=settings.log_level.upper())
for noisy_logger in ("httpx", "httpcore"):
    logging.getLogger(noisy_logger).setLevel(logging.WARNING)

log = logging.getLogger("app.live_mark")

init_db()  # create tables if absent (SQLite locally, Postgres on Render)


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


async def _data_maintenance_loop() -> None:
    """Nightly free-data maintenance, in-process (PRD free-data-pipeline).

    Warms the durable price store + PIT fundamentals for the investable superset, then
    refreshes every model card's headline backtest so stored numbers always come from
    the current engine. Also runs once shortly after boot when the price store is cold
    (fresh deploy / wiped DB) — production primes itself with no manual steps. Same
    resilience contract as the live-mark loop: nothing here can kill the loop, and
    correctness never depends on it (on-demand paths self-heal).
    """
    maint_log = logging.getLogger("app.data_maintenance")

    async def run_all(reason: str) -> None:
        from .jobs import refresh_headlines, warm_prices
        maint_log.info("data maintenance (%s): warming price store + fundamentals", reason)
        warmed = await asyncio.to_thread(warm_prices.run)
        maint_log.info("data maintenance (%s): warm done %s; refreshing headlines", reason, warmed)
        refreshed = await asyncio.to_thread(refresh_headlines.run)
        maint_log.info("data maintenance (%s) complete: refreshed=%s failed=%s", reason,
                       refreshed.get("refreshed"), len(refreshed.get("failed") or []))

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
            await run_all("bootstrap")
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
            await run_all("nightly")
        except asyncio.CancelledError:
            break
        except Exception as exc:  # noqa: BLE001 — keep the loop alive across transient errors
            maint_log.warning("data maintenance error: %s", exc)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()  # idempotent; ensures tables exist when started via uvicorn lifespan
    tasks = []
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
