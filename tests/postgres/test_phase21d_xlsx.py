"""Phase 21D real PostgreSQL migration and attachment pipeline coverage."""

from dataclasses import asdict

from sqlalchemy import func, inspect, select

from app.application.services.attachment_analysis import AttachmentAnalysisService
from app.application.services.attachment_analysis_history import AttachmentAnalysisHistoryService
from app.application.services.attachment_inspection import AttachmentInspectionService
from app.application.services.communication_analysis import CommunicationAnalysisService
from app.application.services.connected_mailbox_attachment_analysis import (
    ConnectedMailboxAttachmentAnalysisService,
)
from app.application.services.identity import IdentityResolver
from app.infrastructure.attachments import FakeAttachmentScanner, SafeAttachmentParser
from app.infrastructure.storage.models import Analysis, BusinessContextRow, WorkflowAction
from app.providers.mock.provider import MockAIProvider
from tests.integration.test_mailbox_attachment_analysis import _connector_for
from tests.postgres.test_connected_mailbox_analysis import (
    _OWNER_SUBJECT,
    _principal,
    _seed_owner_with_gmail_account,
    _uow_factory,
)
from tests.support.connector_factory import StaticCommunicationConnectorFactory
from tests.unit.infrastructure.attachments.fixtures import xlsx_workbook
from tests.unit.infrastructure.storage import (
    test_attachment_analysis_repository as repository_tests,
)
from tests.unit.infrastructure.storage.test_phase21d_migration import exercise_kind_migration


def test_postgres_complete_tabular_result_roundtrip(session_factory):
    repository_tests.test_complete_tabular_result_roundtrip(session_factory)


def test_postgres_corrupt_tabular_result_is_not_trusted(session_factory):
    repository_tests.test_corrupt_tabular_json_is_not_trusted_on_read(session_factory)


def test_postgres_unbounded_tabular_result_is_rejected(session_factory):
    repository_tests.test_unbounded_tabular_result_is_rejected_before_insert(session_factory)


def test_postgres_kind_migration_roundtrip(postgres_engine, postgres_test_url, monkeypatch):
    exercise_kind_migration(postgres_engine, postgres_test_url, monkeypatch)


def test_postgres_xlsx_pipeline_persists_and_reads_structured_result(
    session_factory, postgres_engine
):
    user_id, account = _seed_owner_with_gmail_account(session_factory)
    raw = "PRIVATE_RAW_CELL_21D_876543"
    payload = xlsx_workbook([{"name": "Budget", "rows": [["H", "N"], [raw, 42]]}])
    connector = _connector_for(
        "budget.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", payload
    )
    factory = _uow_factory(session_factory)
    history = AttachmentAnalysisHistoryService(factory)
    service = ConnectedMailboxAttachmentAnalysisService(
        IdentityResolver(factory),
        factory,
        StaticCommunicationConnectorFactory(connector),
        AttachmentAnalysisService(
            AttachmentInspectionService(FakeAttachmentScanner()),
            SafeAttachmentParser(),
            CommunicationAnalysisService(MockAIProvider()),
        ),
        history,
    )
    outcome = service.analyze(_principal(_OWNER_SUBJECT), account.id, "fake-msg-001", "att-1")
    record = history.get_for_user(outcome.record.id, user_id)
    assert record.kind == "xlsx"
    assert record.connector_account_id == account.id
    assert record.provider_message_id == "fake-msg-001"
    assert record.page_count == 1
    assert record.provider == "mock"
    assert raw not in str(asdict(record))
    assert history.list_for_user(
        user_id, 20, 0, connector_account_id=account.id, provider_message_id="fake-msg-001"
    ) == [record]
    columns = {c["name"] for c in inspect(postgres_engine).get_columns("attachment_analyses")}
    assert (
        not {"content", "extracted_text", "workbook_text", "draft_reply", "tabular_json"} & columns
    )
    with session_factory() as session:
        for model in (Analysis, WorkflowAction, BusinessContextRow):
            assert session.scalar(select(func.count()).select_from(model)) == 0
    assert connector.fetch_content_calls == [("fake-msg-001", "att-1")]
