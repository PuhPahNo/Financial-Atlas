import pytest
from sqlalchemy import JSON, Column, Integer, MetaData, Table, create_engine, inspect, select, text

from app.migrations import MIGRATIONS, run_migrations

LEGACY_TABLES = ("paper_fills", "paper_orders", "paper_positions", "paper_portfolios")


def _legacy_schema(engine):
    with engine.begin() as connection:
        for table in LEGACY_TABLES:
            connection.execute(text(f'CREATE TABLE "{table}" (id INTEGER PRIMARY KEY)'))


def test_migration_drops_empty_legacy_tables_once(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    _legacy_schema(engine)

    run_migrations(engine)
    run_migrations(engine)

    tables = set(inspect(engine).get_table_names())
    assert not tables.intersection(LEGACY_TABLES)
    with engine.connect() as connection:
        revisions = connection.execute(text("SELECT revision FROM atlas_schema_migrations")).scalars().all()
    assert revisions == [revision for revision, _upgrade in MIGRATIONS]
    engine.dispose()


def _strategy_schema(engine, *, parameters: dict, defaults: dict) -> None:
    metadata = MetaData()
    strategies = Table(
        "trading_strategies",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("parameters_json", JSON),
        Column("defaults_json", JSON),
    )
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(strategies.insert().values(
            id=1,
            parameters_json=parameters,
            defaults_json=defaults,
        ))


def test_migration_drops_strategy_defaults_only_when_redundant(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'strategy-defaults.db'}")
    _strategy_schema(engine, parameters={"tickers": ["AAPL"]}, defaults={"tickers": ["AAPL"]})

    run_migrations(engine)

    columns = {column["name"] for column in inspect(engine).get_columns("trading_strategies")}
    assert "defaults_json" not in columns
    engine.dispose()


def test_migration_refuses_to_drop_distinct_strategy_defaults(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'strategy-defaults-guard.db'}")
    _strategy_schema(engine, parameters={"window": 20}, defaults={"window": 50})

    with pytest.raises(RuntimeError, match="mismatched strategy ids: 1"):
        run_migrations(engine)

    columns = {column["name"] for column in inspect(engine).get_columns("trading_strategies")}
    assert "defaults_json" in columns
    engine.dispose()


def test_migration_backfills_legacy_null_backtest_status(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'backtest-status.db'}")
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE backtest_runs (id INTEGER PRIMARY KEY, status VARCHAR)"
        ))
        connection.execute(text("INSERT INTO backtest_runs (id, status) VALUES (1, NULL)"))

    run_migrations(engine)

    with engine.connect() as connection:
        status = connection.execute(text(
            "SELECT status FROM backtest_runs WHERE id = 1"
        )).scalar_one()
    assert status == "completed"
    engine.dispose()


def test_migration_removes_only_metrics_duplicated_by_headline(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'headline-metrics.db'}")
    metadata = MetaData()
    strategies = Table(
        "trading_strategies",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("metrics_json", JSON),
    )
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(strategies.insert(), [
            {
                "id": 1,
                "metrics_json": {
                    "_backtest": {"metrics": {"total_return": 0.12}},
                    "backtested_return": 0.12,
                    "max_drawdown": -0.04,
                    "win_rate": 0.6,
                },
            },
            {"id": 2, "metrics_json": {"win_rate": 0.7}},
        ])

    run_migrations(engine)

    with engine.connect() as connection:
        rows = connection.execute(select(strategies.c.id, strategies.c.metrics_json)).all()
    cleaned = dict(rows[0].metrics_json)
    assert cleaned == {"_backtest": {"metrics": {"total_return": 0.12}}}
    assert rows[1].metrics_json == {"win_rate": 0.7}
    engine.dispose()


def test_migration_refuses_to_drop_unexpected_data(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'migration-guard.db'}")
    _legacy_schema(engine)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO paper_orders (id) VALUES (1)"))

    with pytest.raises(RuntimeError, match="paper_orders=1"):
        run_migrations(engine)

    assert set(LEGACY_TABLES).issubset(inspect(engine).get_table_names())
    if "atlas_schema_migrations" in inspect(engine).get_table_names():
        with engine.connect() as connection:
            count = connection.execute(text("SELECT COUNT(*) FROM atlas_schema_migrations")).scalar_one()
        assert count == 0
    engine.dispose()
