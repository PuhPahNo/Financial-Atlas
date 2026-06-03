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
    UniqueConstraint,
    create_engine,
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


def init_db() -> None:
    # Import feature model modules so their tables register with Base before create_all.
    from .models import assistant, paper_trading  # noqa: F401

    Base.metadata.create_all(bind=engine)


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
