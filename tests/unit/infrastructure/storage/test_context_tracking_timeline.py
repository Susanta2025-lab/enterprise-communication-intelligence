"""Portable merged timeline contract, also executed against PostgreSQL."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import event, update

from app.domain.models.business_work_item import WorkItemCommand
from app.infrastructure.storage.models import Analysis, BusinessWorkItemEventRow
from app.infrastructure.storage.repositories.business_context import (
    SqlAlchemyBusinessContextRepository,
)
from app.infrastructure.storage.repositories.business_work_item import (
    SqlAlchemyBusinessWorkItemRepository,
)
from tests.unit.infrastructure.storage.test_business_work_item_repository import (
    context,
    intent,
    owners,
)


def test_move_keeps_genuine_history_and_current_membership(session_factory):
    owner, foreign = owners(session_factory)
    with session_factory() as session:
        a, b = context(session, owner), context(session, owner)
        repo = SqlAlchemyBusinessWorkItemRepository(session)
        item = repo.create_owned(owner, "move", intent(business_context_id=a.id)).item
        original_event = repo.events_owned(item.id, owner)[0]
        item = repo.mutate_owned(
            item.id,
            owner,
            WorkItemCommand(
                operation="edit",
                expected_version=1,
                edit={"title": "Current title, not historical", "business_context_id": b.id},
            ),
        )
        session.commit()
        contexts = SqlAlchemyBusinessContextRepository(session)
        old = contexts.timeline_owned(a, owner, limit=100, offset=0)
        new = contexts.timeline_owned(b, owner, limit=100, offset=0)
        assert any(
            e.id == f"work_item_event:{original_event.id}"
            and e.occurred_at == original_event.occurred_at
            for e in old
        )
        assert "Work item context disassociated" in [e.title for e in old]
        assert "Work item context associated" in [e.title for e in new]
        assert "Work item created" not in [e.title for e in new]
        assert all("Current title" not in e.title for e in old + new)
        assert contexts.timeline_owned(a, foreign, limit=100, offset=0) == []
        assert contexts.get_owned(a.id, foreign) is None
        # Detachment is recorded under B; no hypothetical due/update events.
        repo.mutate_owned(
            item.id,
            owner,
            WorkItemCommand(
                operation="edit",
                expected_version=2,
                edit={"business_context_id": None},
            ),
        )
        session.commit()
        new = contexts.timeline_owned(b, owner, limit=100, offset=0)
        assert "Work item context disassociated" in [e.title for e in new]
        assert len([e for e in new if e.source_type == "work_item"]) == 2


@pytest.mark.parametrize("page_size", [1, 7, 20, 100])
def test_equal_timestamps_paginate_after_merge(session_factory, page_size):
    owner, _ = owners(session_factory)
    with session_factory() as session:
        ctx = context(session, owner)
        repo = SqlAlchemyBusinessWorkItemRepository(session)
        for i in range(53):
            repo.create_owned(owner, f"item-{i}", intent(business_context_id=ctx.id))
        session.execute(update(BusinessWorkItemEventRow).values(occurred_at=ctx.created_at))
        session.commit()
        contexts = SqlAlchemyBusinessContextRepository(session)
        expected = contexts.timeline_owned(ctx, owner, limit=100, offset=0)
        pages = []
        for offset in range(0, len(expected), page_size):
            pages.extend(contexts.timeline_owned(ctx, owner, limit=page_size, offset=offset))
        assert pages == expected
        assert len(expected) == 54
        assert len({e.id for e in pages}) == 54
        assert [e.id for e in pages] == sorted(e.id for e in pages)
        assert all(e.occurred_at == ctx.created_at for e in pages)


def test_representative_volume_returns_one_bounded_projection(session_factory, request):
    owner, foreign = owners(session_factory)
    with session_factory() as session:
        ctx, unrelated = context(session, owner), context(session, foreign)
        repo = SqlAlchemyBusinessWorkItemRepository(session)
        for i in range(250):
            repo.create_owned(owner, f"volume-{i}", intent(business_context_id=ctx.id))
        for i in range(30):
            repo.create_owned(foreign, f"foreign-{i}", intent(business_context_id=unrelated.id))
        # Unrelated owner-wide analysis payloads must never be materialized.
        session.add_all(
            [
                Analysis(
                    id=uuid4(),
                    user_id=owner,
                    provider="mock",
                    priority="low",
                    category="general",
                    source_type="text",
                    summary_text="private",
                    action_items=[],
                    created_at=datetime.now(UTC),
                )
                for _ in range(500)
            ]
        )
        session.commit()
        statements = []

        def capture(conn, cursor, statement, parameters, execution_context, executemany):
            if statement.lstrip().upper().startswith("SELECT"):
                statements.append(statement)

        event.listen(session.bind, "before_cursor_execute", capture)
        try:
            page = SqlAlchemyBusinessContextRepository(session).timeline_owned(
                ctx,
                owner,
                limit=20,
                offset=200,
            )
        finally:
            event.remove(session.bind, "before_cursor_execute", capture)
        assert len(page) == 20
        assert len(statements) == 1
        sql = statements[0].lower()
        assert "union all" in sql and "limit" in sql and "offset" in sql
        assert "business_work_item_events.context_at_event_id" in sql
        assert "business_work_item_events.user_id" in sql
        assert "action_items" not in sql and "summary_text" not in sql
        assert all(e.source_type == "work_item" for e in page)
        if session.bind.dialect.name == "postgresql":
            from app.infrastructure.storage.repositories.context_timeline import timeline_statement

            statement = timeline_statement(ctx, owner, limit=20, offset=200).compile(
                dialect=session.bind.dialect,
                compile_kwargs={"literal_binds": True},
            )
            plan = (
                session.connection()
                .exec_driver_sql("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + str(statement))
                .scalar_one()[0]
            )

            def record_property(name, value):
                request.node.user_properties.append((name, value))

            record_property("timeline_execution_ms", plan["Execution Time"])
            record_property("timeline_planning_ms", plan["Planning Time"])
            record_property("timeline_returned_rows", plan["Plan"]["Actual Rows"])
            record_property(
                "timeline_volume", "250 context events, 30 foreign events, 500 unrelated analyses"
            )
            assert plan["Plan"]["Actual Rows"] == 20


def test_all_categories_merge_without_payloads_or_inferred_membership(session_factory):
    from app.infrastructure.storage.models import (
        AttachmentAnalysisRow,
        BusinessContextCommunicationLinkRow,
        WorkflowAction,
    )

    owner, foreign = owners(session_factory)
    with session_factory() as session:
        ctx = context(session, owner)
        connector, analysis_id = uuid4(), uuid4()
        stamp = ctx.created_at
        session.add(
            BusinessContextCommunicationLinkRow(
                user_id=owner,
                business_context_id=ctx.id,
                connector_account_id=connector,
                provider_message_id="message",
                associated_by_user_id=owner,
                association_source="manual",
                associated_at=stamp,
            )
        )
        for user in (owner, foreign):
            session.add(
                Analysis(
                    id=analysis_id if user == owner else uuid4(),
                    user_id=user,
                    provider="mock",
                    priority="low",
                    category="general",
                    source_type="email",
                    summary_text="private",
                    action_items=[],
                    connector_account_id=connector,
                    message_id="message",
                    created_at=stamp,
                )
            )
        session.add(
            AttachmentAnalysisRow(
                user_id=owner,
                connector_account_id=connector,
                provider_message_id="message",
                provider_attachment_id="attachment",
                filename=" proof.txt ",
                media_type="text/plain",
                kind="txt",
                extracted_content_status="text",
                truncated=False,
                warnings=[],
                summary_text="private",
                priority="low",
                category="general",
                action_items=[],
                provider="mock",
                created_at=stamp,
            )
        )
        session.add(
            WorkflowAction(
                user_id=owner,
                analysis_id=analysis_id,
                action_type="reply",
                status="executed",
                proposed_reply_body="private",
                approved_reply_body="private",
                connector_account_id=connector,
                provider_message_id="message",
                created_at=stamp,
                approved_at=stamp,
                executed_at=stamp,
            )
        )
        repo = SqlAlchemyBusinessWorkItemRepository(session)
        repo.create_owned(owner, "direct", intent(business_context_id=ctx.id))
        repo.create_owned(owner, "unassociated", intent())
        session.execute(update(BusinessWorkItemEventRow).values(occurred_at=stamp))
        session.commit()
        contexts = SqlAlchemyBusinessContextRepository(session)
        entries = contexts.timeline_owned(ctx, owner, limit=100, offset=0)
        assert len(entries) == 8
        assert [e.id for e in entries] == sorted(e.id for e in entries)
        assert sum(e.source_type == "work_item" for e in entries) == 1
        assert sum(e.source_type == "analysis" for e in entries) == 1
        assert next(e.summary for e in entries if e.source_type == "attachment_analysis") == (
            "Attachment analyzed: proof.txt"
        )
        pages = [contexts.timeline_owned(ctx, owner, limit=1, offset=i)[0] for i in range(8)]
        assert pages == entries
