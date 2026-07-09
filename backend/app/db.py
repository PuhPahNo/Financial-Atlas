"""Database layer (PRD 03) — SQLAlchemy engine, session, models.

SQLite locally; Postgres on Render via ``DATABASE_URL`` (PRD 30) — same models,
no code change. A denormalized ``CompanySnapshot`` powers the screener and
watchlist computed columns; raw provider data stays in the filesystem cache.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    inspect,
    text,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

from .core.config import settings

def _normalize_url(url: str) -> str:
    # Render exposes Postgres as postgres:// or postgresql://; SQLAlchemy 2.0 + psycopg3
    # wants the postgresql+psycopg:// driver prefix.
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


_db_url = _normalize_url(settings.database_url)
_is_sqlite = _db_url.startswith("sqlite")
engine = create_engine(
    _db_url,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
    pool_pre_ping=not _is_sqlite,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def _now() -> datetime:
    return datetime.now(timezone.utc)


class CompanySnapshot(Base):
    __tablename__ = "company_snapshots"
    ticker = Column(String, primary_key=True)
    name = Column(String)
    sector = Column(String)
    industry = Column(String)
    price = Column(Float)
    market_cap = Column(Float)
    pe = Column(Float)
    price_to_fcf = Column(Float)
    ev_ebitda = Column(Float)
    dividend_yield = Column(Float)
    net_debt = Column(Float)
    revenue = Column(Float)
    fcf = Column(Float)
    fcf_margin = Column(Float)
    fcf_conversion = Column(Float)
    blended_fair_value = Column(Float)
    margin_of_safety = Column(Float)
    updated_at = Column(DateTime, default=_now, onupdate=_now)


class PitFundamental(Base):
    """Precomputed point-in-time fundamentals (one row per ticker per annual filing).

    Extracted once from EDGAR companyfacts and stored compactly so backtests scanning the
    whole S&P 500 read tiny DB rows instead of re-parsing ~3.7MB of XBRL per ticker. The
    ``filing_date`` is the as-of gate (a row is "known" only on/after it). Values are the
    *originally filed* figures (not later restatements), so a backtest sees exactly what
    an investor could have known on the filing date. ``version`` tracks the extraction
    schema so old rows are transparently re-extracted when fields are added."""
    __tablename__ = "pit_fundamentals"
    __table_args__ = (UniqueConstraint("ticker", "fiscal_year", name="uq_pit_ticker_fy"),)
    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String, nullable=False, index=True)
    fiscal_year = Column(Integer, nullable=False)
    filing_date = Column(String)  # ISO date the figures were first filed
    fcf = Column(Float)
    revenue = Column(Float)
    operating_cash_flow = Column(Float)
    fcf_margin = Column(Float)
    fcf_conversion = Column(Float)
    net_debt = Column(Float)
    net_debt_to_fcf = Column(Float)
    dividends_paid = Column(Float)
    shares = Column(Float)
    # Extended fields (extraction v2) powering F-Score / Magic Formula / quality models.
    net_income = Column(Float)
    gross_profit = Column(Float)
    operating_income = Column(Float)
    total_assets = Column(Float)
    total_current_assets = Column(Float)
    total_current_liabilities = Column(Float)
    long_term_debt = Column(Float)
    shareholder_equity = Column(Float)
    capital_expenditures = Column(Float)
    version = Column(Integer, default=1)
    updated_at = Column(DateTime, default=_now, onupdate=_now)


class PriceSeries(Base):
    """Durable daily price history — one compact JSON row per ticker.

    ``points_json`` holds ``{"dates": [...], "closes": [...]}`` (ascending, dividend/
    split-adjusted closes). Once stored, history is served locally and only the missing
    tail is fetched from providers — backtests and charts stop re-downloading decades of
    bars, which is what keeps the free-tier providers comfortably under quota.
    """
    __tablename__ = "price_series"
    ticker = Column(String, primary_key=True)
    start_date = Column(String)   # ISO first stored bar
    end_date = Column(String)     # ISO last stored bar
    points_json = Column(Text)    # {"dates": [...], "closes": [...]} adjusted closes
    source = Column(String)       # provider that produced the last write
    updated_at = Column(DateTime, default=_now, onupdate=_now)


class Watchlist(Base):
    __tablename__ = "watchlists"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=_now)
    items = relationship("WatchlistItem", cascade="all, delete-orphan", back_populates="watchlist")


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"
    __table_args__ = (UniqueConstraint("watchlist_id", "ticker", name="uq_watchlist_ticker"),)
    id = Column(Integer, primary_key=True, autoincrement=True)
    watchlist_id = Column(Integer, ForeignKey("watchlists.id"), nullable=False)
    ticker = Column(String, nullable=False)
    added_at = Column(DateTime, default=_now)
    watchlist = relationship("Watchlist", back_populates="items")


def _ensure_columns() -> None:
    """Additive micro-migration: CREATE TABLE handles new tables, but existing
    deployments also need new *columns* on old tables. Compare each mapped table
    against the live schema and ALTER TABLE ADD COLUMN anything missing (works on
    both SQLite and Postgres; additive only, never drops or rewrites)."""
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue
            live = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in live:
                    continue
                ddl_type = column.type.compile(engine.dialect)
                conn.execute(text(f'ALTER TABLE {table.name} ADD COLUMN {column.name} {ddl_type}'))


def init_db() -> None:
    # Import feature model modules so their tables register with Base before create_all.
    from .models import assistant, paper_trading, valuation  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _ensure_columns()
    from .migrations import run_migrations
    run_migrations(engine)


@contextmanager
def session_scope():
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()
