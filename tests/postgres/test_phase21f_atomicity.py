"""A commit failure must roll back even an already-flushed XLSX result."""

from dataclasses import replace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.exceptions import PersistenceError
from app.domain.models.tabular_analysis import TabularAnalysisResult
from app.infrastructure.storage.models import (
    AttachmentAnalysisRow,
    BusinessContextRow,
    WorkflowAction,
)
from app.infrastructure.storage.unit_of_work import SqlAlchemyPersistenceUnitOfWork
from tests.postgres.test_attachment_analysis_repository import _create_users, _new_row


def test_xlsx_commit_failure_rolls_back_flushed_result(session_factory, monkeypatch):
    user_id, _ = _create_users(session_factory)
    commit = MagicMock(side_effect=SQLAlchemyError("PRIVATE_SYNTHETIC_COMMIT_DETAIL"))
    monkeypatch.setattr(Session, "commit", commit)
    with pytest.raises(PersistenceError, match="Could not commit persistence changes") as error:
        with SqlAlchemyPersistenceUnitOfWork(session_factory) as uow:
            uow.attachment_analyses.save(replace(
                _new_row(user_id), kind="xlsx", action_items=[],
                tabular_result=TabularAnalysisResult(summary="Synthetic advisory result"),
            ))
            uow.commit()
    commit.assert_called_once()
    assert "PRIVATE_SYNTHETIC" not in str(error.value)
    with session_factory() as session:
        for model in (AttachmentAnalysisRow, WorkflowAction, BusinessContextRow):
            assert session.scalar(select(func.count()).select_from(model)) == 0
