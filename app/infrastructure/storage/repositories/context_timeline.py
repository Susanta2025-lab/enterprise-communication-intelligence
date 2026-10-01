"""Bounded SQL timeline projection: merge before pagination, never load payloads."""

from datetime import UTC

from sqlalchemy import String, cast, func, literal, select, union_all

from app.domain.enums import ContextTimelineEventType
from app.domain.models.context_timeline import ContextTimelineEntry
from app.infrastructure.storage.models import (
    Analysis,
    AttachmentAnalysisRow,
    BusinessContextCommunicationLinkRow,
    BusinessWorkItemEventRow,
    WorkflowAction,
)


def timeline_statement(context, user_id, *, limit, offset, id_collation="C"):
    links = BusinessContextCommunicationLinkRow.__table__
    parts = []

    def entry(
        identity,
        kind,
        occurred,
        title,
        source_type,
        source_id,
        connector=None,
        message=None,
        summary=None,
    ):
        return select(
            identity.label("id"),
            literal(kind).label("type"),
            occurred.label("occurred_at"),
            title.label("title"),
            literal(source_type).label("source_type"),
            source_id.label("source_id"),
            (connector if connector is not None else cast(literal(None), String)).label(
                "connector_account_id"
            ),
            (message if message is not None else literal(None, String)).label(
                "provider_message_id"
            ),
            (summary if summary is not None else literal(None, String)).label("summary"),
        )

    parts.append(
        entry(
            literal(f"context_created:{context.id}"),
            "context_created",
            literal(context.created_at),
            literal("Context created"),
            "business_context",
            literal(str(context.id)),
        )
    )
    if context.archived_at is not None:
        parts.append(
            entry(
                literal(f"context_archived:{context.id}:{context.archived_at.isoformat()}"),
                "context_archived",
                literal(context.archived_at),
                literal("Context archived"),
                "business_context",
                literal(str(context.id)),
                summary=literal(
                    "Current archive state. Historical archive/restore "
                    "transitions are not fully reconstructible."
                ),
            )
        )
    parts.append(
        entry(
            literal("association:") + cast(links.c.id, String),
            "communication_associated",
            links.c.associated_at,
            literal("Communication associated"),
            "communication_link",
            cast(links.c.id, String),
            cast(links.c.connector_account_id, String),
            links.c.provider_message_id,
        ).where(links.c.user_id == user_id, links.c.business_context_id == context.id)
    )

    def linked(table, message):
        return (
            select(links.c.id)
            .where(
                links.c.user_id == user_id,
                links.c.business_context_id == context.id,
                links.c.connector_account_id == table.c.connector_account_id,
                links.c.provider_message_id == message,
            )
            .exists()
        )

    for model, prefix, kind, title, source, message_name in (
        (
            Analysis,
            "analysis:",
            "analysis_completed",
            "Analysis completed",
            "analysis",
            "message_id",
        ),
        (
            AttachmentAnalysisRow,
            "attachment_analysis:",
            "attachment_analysis_completed",
            "Attachment analysis completed",
            "attachment_analysis",
            "provider_message_id",
        ),
    ):
        table = model.__table__
        summary = None
        if model is AttachmentAnalysisRow:
            from sqlalchemy import case

            summary = case(
                (
                    func.length(func.trim(table.c.filename)) > 0,
                    literal("Attachment analyzed: ") + func.trim(table.c.filename),
                ),
                else_="Attachment analyzed",
            )
        parts.append(
            entry(
                literal(prefix) + cast(table.c.id, String),
                kind,
                table.c.created_at,
                literal(title),
                source,
                cast(table.c.id, String),
                cast(table.c.connector_account_id, String),
                table.c[message_name],
                summary,
            ).where(table.c.user_id == user_id, linked(table, table.c[message_name]))
        )

    table = WorkflowAction.__table__
    for suffix, column, kind, title in (
        ("pending", "created_at", "workflow_proposed", "Workflow proposed"),
        ("approved", "approved_at", "workflow_approved", "Workflow approved"),
        ("rejected", "rejected_at", "workflow_rejected", "Workflow rejected"),
        ("executed", "executed_at", "workflow_executed", "Workflow executed"),
        ("failed", "failed_at", "workflow_failed", "Workflow failed"),
    ):
        parts.append(
            entry(
                literal("workflow:") + cast(table.c.id, String) + literal(f":{suffix}"),
                kind,
                table.c[column],
                literal(title),
                "workflow_action",
                cast(table.c.id, String),
                cast(table.c.connector_account_id, String),
                table.c.provider_message_id,
            ).where(
                table.c.user_id == user_id,
                table.c[column].is_not(None),
                linked(table, table.c.provider_message_id),
            )
        )

    table = BusinessWorkItemEventRow.__table__
    parts.append(
        entry(
            literal("work_item_event:") + cast(table.c.id, String),
            "work_item_event",
            table.c.occurred_at,
            literal("Work item ") + func.replace(table.c.event_type, "_", " "),
            "work_item",
            cast(table.c.work_item_id, String),
        ).where(table.c.user_id == user_id, table.c.context_at_event_id == context.id)
    )
    merged = union_all(*parts).subquery()
    return (
        select(merged)
        .order_by(merged.c.occurred_at.desc(), merged.c.id.collate(id_collation))
        .limit(limit)
        .offset(offset)
    )


def read_timeline(session, context, user_id, *, limit, offset):
    rows = session.execute(
        timeline_statement(
            context,
            user_id,
            limit=limit,
            offset=offset,
            id_collation="BINARY" if session.bind.dialect.name == "sqlite" else "C",
        )
    ).mappings()
    result = []
    for row in rows:
        values = dict(row)
        # SQLite stores UUID text without hyphens; public IDs remain canonical.
        from uuid import UUID

        if values["source_id"]:
            source = str(UUID(values["source_id"]))
            values["id"] = values["id"].replace(values["source_id"], source)
            values["source_id"] = source
        if values["type"] == "work_item_event":
            values["id"] = "work_item_event:" + str(UUID(values["id"].split(":")[1]))
        if values["connector_account_id"]:
            values["connector_account_id"] = UUID(values["connector_account_id"])
        if values["occurred_at"].tzinfo is None:
            values["occurred_at"] = values["occurred_at"].replace(tzinfo=UTC)
        values["type"] = ContextTimelineEventType(values["type"])
        result.append(ContextTimelineEntry(**values))
    return result
