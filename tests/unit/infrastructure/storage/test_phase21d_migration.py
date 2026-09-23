"""Kind-constraint migration preserves existing rows and refuses lossy rollback."""

from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import MetaData, Table, create_engine, delete, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from alembic import command
from app.core.exceptions import PersistenceError
from app.domain.schemas import TabularAnalysisResult
from app.infrastructure.storage.models import AttachmentAnalysisRow, User
from app.infrastructure.storage.repositories.attachment_analysis import (
    SqlAlchemyAttachmentAnalysisRepository,
)
from tests.postgres.test_attachment_analysis_repository import _new_row
from tests.unit.infrastructure.storage.test_phase13a_migration import _create_phase12_schema

ROOT = Path(__file__).resolve().parents[4]


def exercise_kind_migration(engine, url, monkeypatch):
    """Exercise the actual revision on either SQLite or disposable PostgreSQL."""
    monkeypatch.setattr(
        "app.infrastructure.storage.migration_config.resolve_migration_database_url",
        lambda: url,
    )
    config = Config(str(ROOT / "alembic.ini"))
    assert ScriptDirectory.from_config(config).get_heads() == ["21d0001"]
    command.downgrade(config, "20c0001")
    sessions = sessionmaker(bind=engine)
    user_id, other_id = uuid4(), uuid4()
    with sessions() as session:
        session.add_all([User(id=user_id), User(id=other_id)])
        session.commit()
    legacy = Table("attachment_analyses", MetaData(), autoload_with=engine)
    before_columns = set(legacy.c.keys())
    before_tables = set(inspect(engine).get_table_names())
    before_constraints = inspect(engine).get_check_constraints("attachment_analyses")
    old_ids = []
    for kind in ("pdf", "docx", "txt", "jpeg", "png"):
        values = asdict(_new_row(user_id))
        values.pop("attachment_analysis_id")
        values.pop("tabular_result")
        values.update(
            id=uuid4(), created_at=datetime.now(UTC), updated_at=datetime.now(UTC), kind=kind
        )
        old_ids.append(values["id"])
        if engine.dialect.name == "sqlite":
            values = {k: v.hex if isinstance(v, type(user_id)) else v for k, v in values.items()}
        with engine.begin() as connection:
            connection.execute(legacy.insert().values(**values))
    with engine.connect() as connection:
        before_rows = connection.execute(select(legacy).order_by(legacy.c.id)).mappings().all()
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            legacy.insert().values(
                **{
                    **values,
                    "id": uuid4().hex if engine.dialect.name == "sqlite" else uuid4(),
                    "kind": "xlsx",
                }
            )
        )
    command.upgrade(config, "21d0001")
    try:
        columns = {c["name"]: c for c in inspect(engine).get_columns("attachment_analyses")}
        assert set(columns) == before_columns | {"tabular_result"}
        assert columns["tabular_result"]["nullable"] is True
        if engine.dialect.name == "postgresql":
            assert str(columns["tabular_result"]["type"]) == "JSONB"
        assert set(inspect(engine).get_table_names()) == before_tables
        with engine.connect() as connection:
            assert (
                connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
                == "21d0001"
            )
            assert (
                connection.execute(select(legacy).order_by(legacy.c.id)).mappings().all()
                == before_rows
            )
        tabular = TabularAnalysisResult(summary="Bounded sample", potential_dates=["2030-01-01"])
        xlsx = replace(
            _new_row(user_id), kind="xlsx", filename="budget.xlsx", tabular_result=tabular
        )
        with sessions() as session:
            repo = SqlAlchemyAttachmentAnalysisRepository(session)
            assert all(repo.get_by_id_for_user(i, user_id).tabular_result is None for i in old_ids)
            new = repo.save(xlsx)
            session.commit()
            assert repo.get_by_id_for_user(new.id, other_id) is None
        with pytest.raises(RuntimeError, match="Cannot downgrade 21d0001"):
            command.downgrade(config, "20c0001")
        with engine.connect() as connection:
            assert (
                connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
                == "21d0001"
            )
        with sessions() as session:
            repo = SqlAlchemyAttachmentAnalysisRepository(session)
            assert repo.get_by_id_for_user(new.id, user_id).tabular_result == tabular
            # Only remove the synthetic XLSX row so the legacy constraint can be restored.
            session.execute(delete(AttachmentAnalysisRow).where(AttachmentAnalysisRow.id == new.id))
            session.commit()
        command.downgrade(config, "20c0001")
        assert {
            c["name"] for c in inspect(engine).get_columns("attachment_analyses")
        } == before_columns
        assert inspect(engine).get_check_constraints("attachment_analyses") == before_constraints
        with engine.connect() as connection:
            assert (
                connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
                == "20c0001"
            )
            assert (
                connection.execute(select(legacy).order_by(legacy.c.id)).mappings().all()
                == before_rows
            )
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(
                legacy.insert().values(
                    **{
                        **values,
                        "id": uuid4().hex if engine.dialect.name == "sqlite" else uuid4(),
                        "kind": "xlsx",
                    }
                )
            )
        command.upgrade(config, "head")
        with sessions() as session:
            repo = SqlAlchemyAttachmentAnalysisRepository(session)
            assert repo.save(xlsx).tabular_result == tabular
            session.commit()
            for kind in ("xls", "xlsm", "xlsb", "csv", "tsv", "unknown"):
                with pytest.raises(PersistenceError):
                    repo.save(replace(xlsx, kind=kind))
                session.rollback()
    finally:
        command.upgrade(config, "head")


def test_sqlite_kind_migration_roundtrip(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{tmp_path / 'phase21d.db'}"
    engine = create_engine(url)
    _create_phase12_schema(engine)
    monkeypatch.setattr(
        "app.infrastructure.storage.migration_config.resolve_migration_database_url",
        lambda: url,
    )
    command.upgrade(Config(str(ROOT / "alembic.ini")), "20c0001")
    try:
        exercise_kind_migration(engine, url, monkeypatch)
    finally:
        engine.dispose()
