import pytest
from sqlalchemy import create_engine, inspect, text

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
    assert revisions == [MIGRATIONS[0][0]]
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
