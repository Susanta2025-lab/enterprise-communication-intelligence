"""Atomic aggregate repository. All writes remain in the caller's transaction."""

from datetime import UTC, datetime
from functools import wraps
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from pydantic import ValidationError
from sqlalchemy import Date, and_, cast, false, func, insert, not_, or_, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.exceptions import PersistenceError
from app.domain.enums import WorkItemSourceKind
from app.domain.exceptions import WorkItemConflictError, WorkItemNotFoundError
from app.domain.interfaces.business_work_item_repository import (
    BusinessWorkItemRepository,
    WorkItemCreationResult,
)
from app.domain.models.business_work_item import BusinessWorkItem, WorkItemCommand
from app.domain.models.business_work_item_event import WorkItemEvent
from app.domain.models.business_work_item_source import WorkItemSource
from app.domain.models.work_item_due import DateDue, TimedDue, stored_due
from app.domain.models.work_item_intent import (
    CreationIntent,
    origin_candidate_key,
    source_key,
    validate_creation_key,
)
from app.domain.models.work_item_query import WorkItemQuery
from app.infrastructure.storage.models import (
    Analysis,
    AttachmentAnalysisRow,
    BusinessContextRow,
    BusinessWorkItemEventRow,
    BusinessWorkItemRow,
    BusinessWorkItemSourceRow,
    ConnectorAccount,
)

_FAILURE = "Could not complete work-item persistence operation."


def _safe_errors(method):
    @wraps(method)
    def wrapped(*args, **kwargs):
        try:
            return method(*args, **kwargs)
        except SQLAlchemyError:
            raise PersistenceError(_FAILURE) from None

    return wrapped


class SqlAlchemyBusinessWorkItemRepository(BusinessWorkItemRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    @_safe_errors
    def get_by_creation_key_owned(self, user_id, creation_key):
        row = self._session.scalars(
            select(BusinessWorkItemRow)
            .where(
                BusinessWorkItemRow.user_id == user_id,
                BusinessWorkItemRow.creation_key == creation_key,
            )
            .execution_options(populate_existing=True)
        ).first()
        return _to_domain(row) if row is not None else None

    def _row(self, item_id, user_id, *, lock=False):
        stmt = (
            select(BusinessWorkItemRow)
            .where(
                BusinessWorkItemRow.id == item_id,
                BusinessWorkItemRow.user_id == user_id,
            )
            .execution_options(populate_existing=True)
        )
        if lock:
            stmt = stmt.with_for_update()
        return self._session.scalars(stmt).first()

    @_safe_errors
    def get_owned(self, item_id: UUID, user_id: UUID) -> BusinessWorkItem | None:
        row = self._row(item_id, user_id)
        return _to_domain(row) if row is not None else None

    @_safe_errors
    def list_owned(self, user_id: UUID, query: WorkItemQuery, now: datetime):
        query = WorkItemQuery.model_validate(query.model_dump())
        if now.utcoffset() is None:
            raise ValueError("reference instant must be aware")
        now = now.astimezone(UTC)
        if query.business_context_id:
            self._context(query.business_context_id, user_id)
        row = BusinessWorkItemRow
        predicates = [row.user_id == user_id]
        if query.archive != "all":
            predicates.append(
                row.archived_at.is_(None)
                if query.archive == "active"
                else row.archived_at.is_not(None)
            )
        for field, value in (
            ("kind", query.kind),
            ("status", query.status),
            ("business_context_id", query.business_context_id),
            ("due_kind", query.effective_due_kind),
        ):
            if value is not None:
                predicates.append(getattr(row, field) == value)
        if query.unassociated:
            predicates.append(row.business_context_id.is_(None))
        for field, lower, upper in (
            (row.due_date, query.due_date_from, query.due_date_to),
            (row.due_at, query.due_at_from, query.due_at_to),
        ):
            if lower is not None:
                predicates.append(field >= lower)
            if upper is not None:
                predicates.append(field <= upper)
        if query.overdue is not None:
            if self._session.get_bind().dialect.name == "postgresql":
                # One SQL statement/snapshot; local calendar date, no fake midnight.
                date_overdue = row.due_date < cast(func.timezone(row.due_timezone, now), Date)
            else:
                # SQLite has no IANA timezone function. Read distinct zone names
                # inside its read transaction, then apply calendar predicates in SQL.
                zones = self._session.scalars(
                    select(row.due_timezone)
                    .where(
                        *predicates,
                        row.due_kind == "date",
                        row.status.in_(("open", "in_progress")),
                        row.archived_at.is_(None),
                    )
                    .distinct()
                ).all()
                date_overdue = or_(
                    false(),
                    *[
                        and_(
                            row.due_timezone == zone,
                            row.due_date < now.astimezone(ZoneInfo(zone)).date(),
                        )
                        for zone in zones
                    ],
                )
            overdue = and_(
                row.archived_at.is_(None),
                row.status.in_(("open", "in_progress")),
                or_(
                    and_(row.due_kind == "date", date_overdue),
                    and_(row.due_kind == "datetime", row.due_at < now),
                ),
            )
            predicates.append(overdue if query.overdue else not_(overdue))
        ordering = (row.created_at.desc(), row.id.desc())
        if query.sort == "due_asc":
            ordering = (row.due_date if query.due_kind == "date" else row.due_at, row.id)
        return tuple(
            _to_domain(r)
            for r in self._session.scalars(
                select(row)
                .where(*predicates)
                .order_by(*ordering)
                .limit(query.limit)
                .offset(query.offset)
            )
        )

    def _existing_creation(self, user_id, key, intent):
        row = self._session.scalars(
            select(BusinessWorkItemRow)
            .where(
                BusinessWorkItemRow.user_id == user_id,
                BusinessWorkItemRow.creation_key == key,
            )
            .execution_options(populate_existing=True)
        ).first()
        if row is not None:
            if row.creation_request_hash != intent.request_hash():
                raise WorkItemConflictError("work_item_creation_key_conflict")
            return WorkItemCreationResult(_to_domain(row), replayed=True)
        if intent.origin_candidate:
            duplicate = self._session.scalar(
                select(BusinessWorkItemRow.id).where(
                    BusinessWorkItemRow.user_id == user_id,
                    BusinessWorkItemRow.origin_candidate_key
                    == origin_candidate_key(intent.origin_candidate),
                )
            )
            if duplicate is not None:
                raise WorkItemConflictError(
                    "work_item_candidate_already_tracked", existing_item_id=duplicate
                )
        return None

    @_safe_errors
    def create_owned(
        self, user_id: UUID, creation_key: str, intent: CreationIntent
    ) -> WorkItemCreationResult:
        validate_creation_key(creation_key)
        # Revalidate at the persistence boundary (also rejects unsafe model_copy changes).
        intent = CreationIntent.model_validate(intent.model_dump())
        existing = self._existing_creation(user_id, creation_key, intent)
        if existing:
            return existing
        try:
            with self._session.begin_nested():
                if intent.business_context_id:
                    self._context(intent.business_context_id, user_id, active=True)
                self._verify_sources(user_id, intent.sources)
                item, events = BusinessWorkItem.create(user_id, creation_key, intent)
                self._session.execute(insert(BusinessWorkItemRow).values(**_values(item)))
                for source in intent.sources:
                    self._session.execute(
                        insert(BusinessWorkItemSourceRow).values(
                            id=uuid4(),
                            work_item_id=item.id,
                            user_id=user_id,
                            **source.model_dump(),
                            source_key=source_key(source),
                            linked_at=item.created_at,
                        )
                    )
                self._append_events(events)
                self._session.flush()
        except IntegrityError:
            # begin_nested has rolled back the loser completely. PostgreSQL is usable.
            existing = self._existing_creation(user_id, creation_key, intent)
            if existing:
                return existing
            raise PersistenceError(_FAILURE) from None
        return WorkItemCreationResult(item, replayed=False)

    @_safe_errors
    def mutate_owned(
        self, item_id: UUID, user_id: UUID, command: WorkItemCommand
    ) -> BusinessWorkItem:
        command = WorkItemCommand.model_validate(command.model_dump(exclude_unset=True))
        with self._session.begin_nested():
            # A row lock makes validated no-ops linearizable too. Still use the
            # owner/version conditional UPDATE as the authoritative write predicate.
            row = self._row(item_id, user_id, lock=True)
            if row is None:
                raise WorkItemNotFoundError()
            old = _to_domain(row)
            updated, events = old.apply(user_id, command)
            if not events:
                return old
            if (
                updated.business_context_id != old.business_context_id
                and updated.business_context_id
            ):
                self._context(updated.business_context_id, user_id, active=True)
            values = _values(updated)
            mutable = {
                k: values[k]
                for k in (
                    "title",
                    "description",
                    "business_context_id",
                    "due_kind",
                    "due_date",
                    "due_at",
                    "due_timezone",
                    "status",
                    "completed_at",
                    "cancelled_at",
                    "archived_at",
                    "updated_at",
                    "version",
                )
            }
            result = self._session.execute(
                update(BusinessWorkItemRow)
                .where(
                    BusinessWorkItemRow.id == item_id,
                    BusinessWorkItemRow.user_id == user_id,
                    BusinessWorkItemRow.version == command.expected_version,
                )
                .values(**mutable)
                .execution_options(synchronize_session=False)
            )
            if result.rowcount != 1:
                raise WorkItemConflictError("work_item_version_conflict")
            self._append_events(events)
            self._session.flush()
            return updated

    def _append_events(self, events):
        for event in events:
            values = event.model_dump(exclude={"owner_user_id", "metadata"})
            values["user_id"] = event.owner_user_id
            values["metadata"] = event.metadata.model_dump(mode="json", exclude_none=True)
            # Context metadata requires explicit null endpoints.
            if event.event_type in ("context_associated", "context_disassociated"):
                values["metadata"] = event.metadata.model_dump(mode="json")
            self._session.execute(insert(BusinessWorkItemEventRow.__table__).values(**values))

    def _context(self, context_id, user_id, *, active=False):
        stmt = (
            select(BusinessContextRow)
            .where(
                BusinessContextRow.id == context_id,
                BusinessContextRow.user_id == user_id,
            )
            .execution_options(populate_existing=True)
        )
        if active:
            # FOR UPDATE conflicts with the existing save_owned SQL UPDATE's
            # NO KEY UPDATE lock. KEY SHARE would not serialize archive writes.
            stmt = stmt.with_for_update()
        row = self._session.scalars(stmt).first()
        if row is None:
            raise WorkItemNotFoundError()
        if active and row.status != "active":
            raise WorkItemConflictError("work_item_context_archived")
        return row

    def _verify_sources(self, user_id, sources):
        """Validate owned persisted references only; no candidate projection or I/O."""
        for source in sources:
            if source.connector_account_id:
                account = self._session.scalar(
                    select(ConnectorAccount.id).where(
                        ConnectorAccount.id == source.connector_account_id,
                        ConnectorAccount.user_id == user_id,
                    )
                )
                if account is None:
                    raise WorkItemNotFoundError()
            if source.source_kind == WorkItemSourceKind.COMMUNICATION:
                continue
            cls = Analysis if source.analysis_id else AttachmentAnalysisRow
            source_id = source.analysis_id or source.attachment_analysis_id
            row = self._session.scalars(
                select(cls).where(cls.id == source_id, cls.user_id == user_id)
            ).first()
            if row is None:
                raise WorkItemNotFoundError()
            message_id = row.message_id if source.analysis_id else row.provider_message_id
            if (source.connector_account_id, source.provider_message_id) != (
                row.connector_account_id,
                message_id if row.connector_account_id else None,
            ):
                raise WorkItemNotFoundError()
            if source.attachment_analysis_id:
                if source.provider_attachment_id != row.provider_attachment_id:
                    raise WorkItemNotFoundError()
                allowed = (
                    ("potential_action_mentions", "potential_dates")
                    if row.kind == "xlsx"
                    else ("action_items",)
                )
                if source.candidate_field is not None and source.candidate_field not in allowed:
                    raise ValueError("candidate field does not match attachment kind")

    @_safe_errors
    def sources_owned(self, item_id: UUID, user_id: UUID) -> tuple[WorkItemSource, ...]:
        if self._row(item_id, user_id) is None:
            raise WorkItemNotFoundError()
        rows = self._session.scalars(
            select(BusinessWorkItemSourceRow)
            .where(
                BusinessWorkItemSourceRow.work_item_id == item_id,
                BusinessWorkItemSourceRow.user_id == user_id,
            )
            .order_by(BusinessWorkItemSourceRow.source_key)
            .limit(11)
        ).all()
        try:
            sources = tuple(
                WorkItemSource.model_validate(
                    {f: getattr(r, f) for f in WorkItemSource.model_fields}
                )
                for r in rows
            )
            if len(sources) > 10:
                raise ValueError("invalid stored source count")
            return sources
        except (ValueError, ValidationError):
            raise PersistenceError(_FAILURE) from None

    @_safe_errors
    def events_owned(self, item_id: UUID, user_id: UUID, *, limit=20, offset=0):
        _page(limit, offset)
        if self._row(item_id, user_id) is None:
            raise WorkItemNotFoundError()
        table = BusinessWorkItemEventRow.__table__
        stmt = select(table).where(table.c.work_item_id == item_id, table.c.user_id == user_id)
        stmt = stmt.order_by(table.c.item_version, table.c.event_ordinal, table.c.id)
        return tuple(
            _event_domain(r)
            for r in self._session.execute(stmt.limit(limit).offset(offset)).mappings()
        )

    @_safe_errors
    def context_events_owned(self, context_id: UUID, user_id: UUID, *, limit=20, offset=0):
        _page(limit, offset)
        self._context(context_id, user_id)
        table = BusinessWorkItemEventRow.__table__
        stmt = select(table).where(
            table.c.context_at_event_id == context_id, table.c.user_id == user_id
        )
        stmt = stmt.order_by(table.c.occurred_at.desc(), table.c.id)
        return tuple(
            _event_domain(r)
            for r in self._session.execute(stmt.limit(limit).offset(offset)).mappings()
        )


def _page(limit, offset):
    if type(limit) is not int or type(offset) is not int or not 1 <= limit <= 100 or offset < 0:
        raise ValueError("invalid page bounds")


def _utc(value):
    return (
        value.replace(tzinfo=UTC) if isinstance(value, datetime) and value.tzinfo is None else value
    )


def _values(item):
    values = item.model_dump(exclude={"due", "owner_user_id"})
    values.update(
        user_id=item.owner_user_id,
        due_kind=item.due.kind,
        due_date=None,
        due_at=None,
        due_timezone=None,
    )
    if isinstance(item.due, DateDue):
        values.update(due_date=item.due.date, due_timezone=item.due.timezone)
    elif isinstance(item.due, TimedDue):
        values.update(due_at=item.due.at.astimezone(UTC), due_timezone=item.due.timezone)
    return values


def _to_domain(row):
    try:
        values = {
            f: _utc(getattr(row, f))
            for f in BusinessWorkItem.model_fields
            if f not in ("due", "owner_user_id")
        }
        due = {"kind": row.due_kind}
        if row.due_kind != "none":
            due["timezone"] = row.due_timezone
            due["date" if row.due_kind == "date" else "at"] = (
                row.due_date if row.due_kind == "date" else row.due_at
            )
        return BusinessWorkItem(owner_user_id=row.user_id, due=stored_due(due), **values)
    except (ValueError, ValidationError):
        raise PersistenceError(_FAILURE) from None


def _event_domain(row):
    try:
        values = dict(row)
        values["owner_user_id"] = values.pop("user_id")
        values["occurred_at"] = _utc(values["occurred_at"])
        return WorkItemEvent.model_validate(values)
    except (ValueError, ValidationError):
        raise PersistenceError(_FAILURE) from None
