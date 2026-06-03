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

    # Cache (PRD 05). Filesystem locally.
    cache_dir: Path = BACKEND_ROOT / ".cache"
    cache_enabled: bool = True

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
    # Reserved for the future paper-trading / backtesting phase (Alpaca).
    alpaca_api_key: str = ""
    alpaca_secret: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
