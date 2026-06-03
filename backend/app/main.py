"""FastAPI application entrypoint (PRD 01, 04)."""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api import assistant, backtesting, paper_trading
from .api.routes import router
from .core.config import settings
from .core.errors import AtlasError
from .db import init_db

logging.basicConfig(level=settings.log_level.upper())
for noisy_logger in ("httpx", "httpcore"):
    logging.getLogger(noisy_logger).setLevel(logging.WARNING)

init_db()  # create tables if absent (SQLite locally, Postgres on Render)

app = FastAPI(title="Financial Atlas API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
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
    return {"status": "ok", "env": settings.env, "version": app.version}
