"""FastAPI application entrypoint (PRD 01, 04)."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

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


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()  # idempotent; ensures tables exist when started via uvicorn lifespan
    task = asyncio.create_task(_live_mark_loop()) if settings.live_mark_enabled else None
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
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
