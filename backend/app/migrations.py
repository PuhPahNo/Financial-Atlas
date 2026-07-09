"""Small linear schema migration runner for SQLite and Postgres.

Migrations run inside the same transaction that records their revision. Destructive
steps must validate their preconditions first so a surprising production state fails
closed and leaves the previous Render instance live.
"""
from __future__ import annotations

from collections.abc import Callable
import logging

from sqlalchemy import Connection, Engine, inspect, text

logger = logging.getLogger(__name__)

Migration = tuple[str, Callable[[Connection], None]]

_LEGACY_PAPER_TABLES = (
    "paper_fills",
    "paper_orders",
    "paper_positions",
    "paper_portfolios",
)


def _drop_empty_legacy_paper_tables(connection: Connection) -> None:
    existing = set(inspect(connection).get_table_names())
    present = [table for table in _LEGACY_PAPER_TABLES if table in existing]
    counts = {
        table: int(connection.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar_one())
        for table in present
    }
    nonempty = {table: count for table, count in counts.items() if count}
    if nonempty:
        details = ", ".join(f"{table}={count}" for table, count in nonempty.items())
        raise RuntimeError(f"Refusing to drop non-empty legacy paper tables: {details}")
    for table in present:
        connection.execute(text(f'DROP TABLE "{table}"'))


MIGRATIONS: tuple[Migration, ...] = (
    ("20260709_01_drop_empty_legacy_paper_tables", _drop_empty_legacy_paper_tables),
)


def run_migrations(db_engine: Engine) -> None:
    with db_engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE IF NOT EXISTS atlas_schema_migrations ("
            "revision VARCHAR(128) PRIMARY KEY, applied_at TIMESTAMP NOT NULL)"
        ))
        applied = {
            row[0]
            for row in connection.execute(text("SELECT revision FROM atlas_schema_migrations"))
        }
        for revision, upgrade in MIGRATIONS:
            if revision in applied:
                continue
            upgrade(connection)
            connection.execute(
                text(
                    "INSERT INTO atlas_schema_migrations (revision, applied_at) "
                    "VALUES (:revision, CURRENT_TIMESTAMP)"
                ),
                {"revision": revision},
            )
            logger.info("applied schema migration %s", revision)
