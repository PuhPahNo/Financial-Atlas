"""Typed application settings (PRD 01 §6).

All configuration flows through this single object, sourced from environment
variables (with sensible local-first defaults). No secrets live in code.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    # Read the project-root .env (where keys live) then backend/.env (overrides).
    model_config = SettingsConfigDict(
        env_file=(str(BACKEND_ROOT.parent / ".env"), str(BACKEND_ROOT / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = "local"
    log_level: str = "info"

    # SEC requires a descriptive User-Agent with contact info (PRD 02 §7).
    sec_user_agent: str = "Financial Atlas you@example.com"

    # Cache (PRD 05). Filesystem locally; point CACHE_DIR at a mounted disk in production
    # to persist across restarts. CACHE_MAX_MB caps the on-disk size (0 = unlimited) so a
    # small disk can't overflow with raw EDGAR companyfacts.
    cache_dir: Path = BACKEND_ROOT / ".cache"
    cache_enabled: bool = True
    cache_max_mb: int = 0

    # Database (PRD 03). SQLite locally -> Postgres on Render via DATABASE_URL.
    database_url: str = f"sqlite:///{BACKEND_ROOT / 'atlas.db'}"

    # CORS for the local Next.js dev server.
    frontend_origin: str = "http://localhost:3000"

    # Optional provider API keys (all blank by default => those providers self-disable).
    fmp_api_key: str = ""
    alpha_vantage_api_key: str = ""
    twelve_data_api_key: str = ""
    finnhub_api_key: str = ""
    fred_api_key: str = ""
    openai_api_key: str = ""
    openai_model: str = "gpt-5.5"
    auth_required: bool = True
    auth_username: str = "admin"
    auth_password: str = "admin123"
    auth_secret: str = "dev-atlas-auth-secret-change-me"
    auth_cookie_name: str = "atlas_session"
    auth_session_ttl_seconds: int = 7 * 24 * 60 * 60
    paper_trading_rate_limit_per_minute: int = 240
    assistant_rate_limit_per_minute: int = 20
    auth_rate_limit_per_minute: int = 12

    # Live-ish paper trader valuation (PRD live-paper-valuation). The in-process refresh
    # tick pre-warms account marks during market hours; quotes are short-cached so reads
    # within a refresh window coalesce. Yahoo is ~15-min delayed, so faster than ~60s is
    # pointless. Set live_mark_enabled=false to disable the background tick (read path
    # still serves correct values on demand).
    live_mark_enabled: bool = True
    live_mark_interval_seconds: int = 60
    live_quote_ttl_seconds: int = 60

    # Backtests scan the S&P 500 as it was on each historical date (point-in-time membership
    # reconstructed free from the published change-log). Set false to scan today's list only.
    backtest_point_in_time_membership: bool = True
    # Safety backstop on how many tickers a single backtest scans (0 = unlimited). The engine
    # is memory-lean enough for the full universe on 512MB, but this caps a pathological run.
    backtest_universe_max: int = 0
    # Reserved for the future paper-trading / backtesting phase (Alpaca).
    alpaca_api_key: str = ""
    alpaca_secret: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
