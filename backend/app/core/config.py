"""Typed application settings (PRD 01 §6).

All configuration flows through this single object, sourced from environment
variables (with sensible local-first defaults). No secrets live in code.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]

# Dev-only fallbacks. Production refuses to boot while these are in effect (see
# Settings._require_production_secrets) so a missed env var can never ship the
# well-known repo defaults.
DEV_AUTH_PASSWORD = "admin123"
DEV_AUTH_SECRET = "dev-atlas-auth-secret-change-me"


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
    # small disk can't overflow with raw EDGAR companyfacts (~3.7MB each). Defaults to a
    # conservative cap because an unbounded cache filled small ephemeral disks and made
    # writes raise OSError; raise it when CACHE_DIR points at a large mounted disk.
    cache_dir: Path = BACKEND_ROOT / ".cache"
    cache_enabled: bool = True
    cache_max_mb: int = 512

    # Database (PRD 03). SQLite locally -> Postgres on Render via DATABASE_URL.
    database_url: str = f"sqlite:///{BACKEND_ROOT / 'atlas.db'}"

    # CORS for the local Next.js dev server.
    frontend_origin: str = "http://localhost:3000"

    # Optional provider API keys (all blank by default => those providers self-disable).
    fmp_api_key: str = ""
    # Daily FMP call budget (free tier ≈ 250/day). Real network calls past this raise a
    # RateLimitError so chains degrade to keyless providers instead of exhausting the key.
    # Kept under the hard cap to leave headroom for interactive use. 0 disables the guard.
    fmp_daily_budget: int = 180
    alpha_vantage_api_key: str = ""
    twelve_data_api_key: str = ""
    finnhub_api_key: str = ""
    fred_api_key: str = ""
    openai_api_key: str = ""
    openai_model: str = "gpt-5.5"
    auth_required: bool = True
    auth_username: str = "admin"
    auth_password: str = DEV_AUTH_PASSWORD
    auth_secret: str = DEV_AUTH_SECRET
    auth_cookie_name: str = "atlas_session"
    auth_session_ttl_seconds: int = 7 * 24 * 60 * 60
    paper_trading_rate_limit_per_minute: int = 240
    assistant_rate_limit_per_minute: int = 20

    # Live-ish paper trader valuation (PRD live-paper-valuation). The in-process refresh
    # tick pre-warms account marks during market hours; quotes are short-cached so reads
    # within a refresh window coalesce. Yahoo is ~15-min delayed, so faster than ~60s is
    # pointless. Set live_mark_enabled=false to disable the background tick (read path
    # still serves correct values on demand).
    live_mark_enabled: bool = True
    live_mark_interval_seconds: int = 60
    live_quote_ttl_seconds: int = 60

    # Nightly in-process data maintenance (PRD free-data-pipeline): warms the durable
    # price store + PIT fundamentals, then refreshes every model card's headline backtest
    # on the current engine. Runs inside the single web service (same pattern as the
    # live-mark loop — no extra Render service). Also bootstraps once shortly after boot
    # when the price store is cold (fresh deploy / wiped DB) so cards self-populate.
    data_maintenance_enabled: bool = True
    data_maintenance_utc_hour: int = 8  # 08:30 UTC ≈ hours before the US open

    # Backtests scan the S&P 500 as it was on each historical date (point-in-time membership
    # reconstructed free from the published change-log). Set false to scan today's list only.
    backtest_point_in_time_membership: bool = True
    # Safety backstop on how many tickers a single backtest scans (0 = unlimited). The engine
    # is memory-lean enough for the full universe on 512MB, but this caps a pathological run.
    backtest_universe_max: int = 0
    # Reserved for the future paper-trading / backtesting phase (Alpaca).
    alpaca_api_key: str = ""
    alpaca_secret: str = ""

    @model_validator(mode="after")
    def _require_production_secrets(self) -> "Settings":
        """Fail closed: never serve production traffic on the committed dev AUTH_SECRET.

        AUTH_SECRET signs session cookies — anyone who has read this repo could forge a
        valid session if production ever ran on the committed fallback, bypassing the
        password entirely, so it must differ from the dev value. AUTH_PASSWORD only has
        to be non-blank: its strength is the operator's deliberate choice (2026-06-09).
        """
        if self.env.lower() not in {"production", "prod", "staging"} or not self.auth_required:
            return self
        missing = []
        if not self.auth_password:
            missing.append("AUTH_PASSWORD")
        if self.auth_secret in ("", DEV_AUTH_SECRET):
            missing.append("AUTH_SECRET")
        if missing:
            raise ValueError(
                f"Refusing to start with default/blank credentials in env={self.env!r}: "
                f"set {', '.join(missing)} (or set AUTH_REQUIRED=false to run without auth)."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
