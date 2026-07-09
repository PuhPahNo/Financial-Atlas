"""Small linear schema migration runner for SQLite and Postgres.

Migrations run inside the same transaction that records their revision. Destructive
steps must validate their preconditions first so a surprising production state fails
closed and leaves the previous Render instance live.
"""
from __future__ import annotations

from collections.abc import Callable
import logging

from sqlalchemy import Connection, Engine, MetaData, Table, inspect, select, text

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


def _drop_redundant_strategy_defaults(connection: Connection) -> None:
    inspector = inspect(connection)
    if "trading_strategies" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("trading_strategies")}
    if "defaults_json" not in columns:
        return

    strategies = Table("trading_strategies", MetaData(), autoload_with=connection)
    mismatched_ids = [
        row.id
        for row in connection.execute(select(
            strategies.c.id,
            strategies.c.parameters_json,
            strategies.c.defaults_json,
        ))
        if (row.defaults_json or {}) != (row.parameters_json or {})
    ]
    if mismatched_ids:
        sample = ", ".join(str(strategy_id) for strategy_id in mismatched_ids[:10])
        raise RuntimeError(
            "Refusing to drop non-redundant trading_strategies.defaults_json; "
            f"mismatched strategy ids: {sample}"
        )
    connection.execute(text('ALTER TABLE "trading_strategies" DROP COLUMN "defaults_json"'))


def _normalize_backtest_status(connection: Connection) -> None:
    inspector = inspect(connection)
    if "backtest_runs" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("backtest_runs")}
    if "status" not in columns:
        return
    connection.execute(text(
        'UPDATE "backtest_runs" SET "status" = \'completed\' WHERE "status" IS NULL'
    ))
    if connection.dialect.name == "postgresql":
        connection.execute(text(
            'ALTER TABLE "backtest_runs" ALTER COLUMN "status" SET NOT NULL'
        ))


def _remove_duplicated_headline_metrics(connection: Connection) -> None:
    inspector = inspect(connection)
    if "trading_strategies" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("trading_strategies")}
    if "metrics_json" not in columns:
        return

    strategies = Table("trading_strategies", MetaData(), autoload_with=connection)
    legacy_keys = {"backtested_return", "max_drawdown", "win_rate"}
    for row in connection.execute(select(strategies.c.id, strategies.c.metrics_json)):
        metrics = dict(row.metrics_json or {})
        if "_backtest" not in metrics or not legacy_keys.intersection(metrics):
            continue
        for key in legacy_keys:
            metrics.pop(key, None)
        connection.execute(
            strategies.update().where(strategies.c.id == row.id).values(metrics_json=metrics)
        )


MIGRATIONS: tuple[Migration, ...] = (
    ("20260709_01_drop_empty_legacy_paper_tables", _drop_empty_legacy_paper_tables),
    ("20260709_02_drop_redundant_strategy_defaults", _drop_redundant_strategy_defaults),
    ("20260709_03_normalize_backtest_status", _normalize_backtest_status),
    ("20260709_04_remove_duplicated_headline_metrics", _remove_duplicated_headline_metrics),
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
