"""Additive upgrade, retained Phase 21 JSON, safe downgrade and schema parity."""

from dataclasses import replace
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import inspect, select, text

from alembic import command
from app.domain.schemas import TabularAnalysisResult
from app.infrastructure.storage.database import create_database_engine, create_session_factory
from app.infrastructure.storage.models import AttachmentAnalysisRow, Base, User
from app.infrastructure.storage.repositories.attachment_analysis import (
    SqlAlchemyAttachmentAnalysisRepository,
)
from app.infrastructure.storage.repositories.business_work_item import (
    SqlAlchemyBusinessWorkItemRepository,
)
from tests.postgres.test_attachment_analysis_repository import _new_row
from tests.unit.infrastructure.storage.test_business_work_item_repository import TABLES, intent
from tests.unit.infrastructure.storage.test_phase13a_migration import _create_phase12_schema

ROOT = Path(__file__).resolve().parents[4]


def exercise_tracking_migration(engine, url, monkeypatch):
    monkeypatch.setattr(
        "app.infrastructure.storage.migration_config.resolve_migration_database_url", lambda: url
    )
    config = Config(str(ROOT / "alembic.ini"))
    command.downgrade(config, "21d0001")
    sessions = create_session_factory(engine)
    with sessions() as session:
        owner = User()
        session.add(owner)
        session.flush()
        owner_id = owner.id
        original = SqlAlchemyAttachmentAnalysisRepository(session).save(
            replace(
                _new_row(owner_id),
                kind="xlsx",
                tabular_result=TabularAnalysisResult(
                    summary="Retained", potential_dates=["2030-01-01"]
                ),
            )
        )
        session.commit()
    with engine.connect() as connection:
        before = dict(connection.execute(select(AttachmentAnalysisRow.__table__)).mappings().one())
    old_tables = set(inspect(engine).get_table_names())
    command.upgrade(config, "22b0001")
    inspector = inspect(engine)
    assert set(inspector.get_table_names()) == old_tables | {
        t.__tablename__ if hasattr(t, "__tablename__") else t.__table__.name for t in TABLES
    }
    for cls in TABLES:
        table = cls.__table__
        assert {c["name"] for c in inspector.get_columns(table.name)} == set(table.c.keys())
        assert {i["name"] for i in inspector.get_indexes(table.name)} >= {
            i.name for i in table.indexes
        }
        expected = {
            c.name
            for c in table.constraints
            if c.__class__.__name__ == "CheckConstraint"
            and (not c.name.endswith("_pg") or engine.dialect.name == "postgresql")
            and (not c.name.endswith("_sqlite") or engine.dialect.name == "sqlite")
        }
        assert {c["name"] for c in inspector.get_check_constraints(table.name)} == expected
    with engine.connect() as connection:
        assert (
            dict(connection.execute(select(AttachmentAnalysisRow.__table__)).mappings().one())
            == before
        )
    with sessions() as session:
        assert (
            SqlAlchemyAttachmentAnalysisRepository(session)
            .get_by_id_for_user(original.id, owner_id)
            .tabular_result.summary
            == "Retained"
        )
    command.downgrade(config, "21d0001")
    assert set(inspect(engine).get_table_names()) == old_tables
    command.upgrade(config, "head")
    with sessions() as session:
        saved = (
            SqlAlchemyBusinessWorkItemRepository(session)
            .create_owned(owner_id, "key", intent())
            .item
        )
        session.commit()
    with pytest.raises(RuntimeError, match="Cannot downgrade 22b0001"):
        command.downgrade(config, "21d0001")
    with sessions() as session:
        assert SqlAlchemyBusinessWorkItemRepository(session).get_owned(saved.id, owner_id) == saved
        assert (
            session.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            == "22b0001"
        )
    assert all(t.__table__.name in inspect(engine).get_table_names() for t in TABLES)


def test_sqlite_tracking_migration(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{tmp_path / 'disposable_phase22b.db'}"
    engine = create_database_engine(url)
    _create_phase12_schema(engine)
    monkeypatch.setattr(
        "app.infrastructure.storage.migration_config.resolve_migration_database_url", lambda: url
    )
    command.upgrade(Config(str(ROOT / "alembic.ini")), "21d0001")
    try:
        exercise_tracking_migration(engine, url, monkeypatch)
    finally:
        engine.dispose()


@pytest.mark.parametrize("populated", range(3))
def test_downgrade_inspects_all_tables_before_ddl(monkeypatch, populated):
    # Load the standalone migration, without importing the application's models.
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "phase22b", ROOT / "alembic/versions/22b0001_business_work_items.py"
    )
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    inspected = []
    dropped = []

    class Result:
        def first(self):
            return (1,) if len(inspected) - 1 == populated else None

    class Connection:
        from types import SimpleNamespace

        dialect = SimpleNamespace(name="sqlite")

        def execute(self, stmt):
            inspected.append(str(stmt))
            return Result()

    monkeypatch.setattr(revision.op, "get_bind", lambda: Connection())
    monkeypatch.setattr(revision.op, "drop_table", dropped.append)
    with pytest.raises(RuntimeError, match="tracking data"):
        revision.downgrade()
    assert len(inspected) == 3 and not dropped


def test_metadata_sqlite_postgres_ddl_compiles():
    from sqlalchemy.dialects import postgresql, sqlite
    from sqlalchemy.schema import CreateTable

    for cls in TABLES:
        for dialect in (postgresql.dialect(), sqlite.dialect()):
            sql = str(
                CreateTable(Base.metadata.tables[cls.__table__.name]).compile(dialect=dialect)
            )
            assert "CREATE TABLE" in sql
            if cls.__table__.name == "business_work_items":
                assert ("NOT GLOB" in sql) == (dialect.name == "sqlite")
                assert ("creation_key !~" in sql) == (dialect.name == "postgresql")
