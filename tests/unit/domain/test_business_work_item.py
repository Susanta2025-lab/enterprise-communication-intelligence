"""ADR-030 domain, canonicalization, lifecycle and privacy boundaries."""

from datetime import UTC, datetime
from itertools import product
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.domain.enums import WorkItemStatus
from app.domain.exceptions import WorkItemConflictError, WorkItemNotFoundError
from app.domain.models.business_work_item import BusinessWorkItem, WorkItemCommand
from app.domain.models.business_work_item_event import WorkItemEvent
from app.domain.models.business_work_item_source import CandidateLocator, WorkItemSource
from app.domain.models.work_item_due import DUE_ADAPTER, due_json, stored_due
from app.domain.models.work_item_intent import CreationIntent, source_key, validate_creation_key


def item(**kwargs):
    return BusinessWorkItem.create(
        uuid4(), "key", CreationIntent(kind="action", title=" Track ", **kwargs)
    )[0]


def apply(current, operation, **kwargs):
    return current.apply(
        current.owner_user_id,
        WorkItemCommand(
            operation=operation,
            expected_version=current.version,
            **kwargs,
        ),
    )


@pytest.mark.parametrize(
    "old,new,reopen", list(product(WorkItemStatus, WorkItemStatus, (False, True)))
)
def test_transition_matrix(old, new, reopen):
    current = item()
    if old != WorkItemStatus.OPEN:
        current, _ = apply(current, "status", status=old)
    terminal = old in (WorkItemStatus.COMPLETED, WorkItemStatus.CANCELLED)
    reopening = terminal and new == WorkItemStatus.OPEN
    allowed = (not terminal or new == old or reopening) and reopen == reopening
    if not allowed:
        with pytest.raises(WorkItemConflictError):
            apply(current, "status", status=new, reopen=reopen)
        return
    updated, events = apply(current, "status", status=new, reopen=reopen)
    assert updated.status == new
    assert updated.version == current.version + (old != new)
    assert len(events) == (old != new)
    assert (updated.completed_at is not None) == (new == WorkItemStatus.COMPLETED)
    assert (updated.cancelled_at is not None) == (new == WorkItemStatus.CANCELLED)


@pytest.mark.parametrize("status", list(WorkItemStatus))
def test_archive_restore_and_edit_guards(status):
    current = item()
    if status != WorkItemStatus.OPEN:
        current, _ = apply(current, "status", status=status)
    archived, events = apply(current, "archive")
    assert archived.status == status and archived.archived_at and len(events) == 1
    assert apply(archived, "archive") == (archived, ())
    for command in (dict(operation="edit", edit={}), dict(operation="status", status=status)):
        with pytest.raises(WorkItemConflictError):
            apply(archived, **command)
    restored, events = apply(archived, "restore")
    assert restored.archived_at is None and restored.status == status
    assert apply(restored, "restore") == (restored, ())
    if status in (WorkItemStatus.COMPLETED, WorkItemStatus.CANCELLED):
        with pytest.raises(WorkItemConflictError):
            apply(restored, "edit", edit={})
    else:
        assert apply(restored, "edit", edit={}) == (restored, ())


def test_noop_still_checks_owner_and_version():
    current = item()
    with pytest.raises(WorkItemNotFoundError):
        current.apply(uuid4(), WorkItemCommand(operation="restore", expected_version=1))
    with pytest.raises(WorkItemConflictError, match="version"):
        current.apply(
            current.owner_user_id, WorkItemCommand(operation="restore", expected_version=2)
        )
    for field, value in (
        ("kind", "obligation"),
        ("owner_user_id", uuid4()),
        ("creation_key", "other"),
    ):
        with pytest.raises(ValidationError):
            setattr(current, field, value)


@pytest.mark.parametrize(
    "due",
    [
        {"kind": "none", "timezone": "UTC"},
        {"kind": "none", "date": None},
        {"kind": "date", "date": "2026-02-30", "timezone": "UTC"},
        {"kind": "date", "date": "20260201", "timezone": "UTC"},
        {"kind": "date", "date": "2026-02-01", "timezone": ""},
        {"kind": "date", "date": "2026-02-01", "timezone": "Mars/Future"},
        {"kind": "date", "date": "2026-02-01", "timezone": "UTC", "at": None},
        {"kind": "datetime", "at": "2026-03-29T01:30:00+00:00", "timezone": "Europe/London"},
        {"kind": "datetime", "at": "2026-01-01T12:00:00+01:00", "timezone": "Europe/London"},
        {"kind": "datetime", "at": "2026-11-01T01:30:00", "timezone": "America/New_York"},
        {"kind": "datetime", "at": 1780000000, "timezone": "UTC"},
        {"kind": "datetime", "at": "2026-01-01 12:00:00Z", "timezone": "UTC"},
        {"kind": "datetime", "at": "2026-10-04T02:15:00+10:30", "timezone": "Australia/Lord_Howe"},
        {"kind": "datetime", "at": "2011-12-30T12:00:00-10:00", "timezone": "Pacific/Apia"},
    ],
)
def test_invalid_due_values(due):
    with pytest.raises((ValidationError, ValueError)):
        DUE_ADAPTER.validate_python(due)


@pytest.mark.parametrize("offset", ["-04:00", "-05:00"])
def test_ambiguous_time_explicit_offset(offset):
    due = DUE_ADAPTER.validate_python(
        {"kind": "datetime", "at": f"2026-11-01T01:30:00{offset}", "timezone": "America/New_York"}
    )
    assert stored_due(due_json(due)) == due
    assert due_json(due)["at"].endswith(".000000Z")


def test_date_only_overdue_and_skipped_calendar_day():
    current = item(due={"kind": "date", "date": "2011-12-30", "timezone": "Pacific/Apia"})
    assert due_json(current.due)["date"] == "2011-12-30"
    assert not current.overdue(datetime(2011, 12, 30, 9, 59, tzinfo=UTC))
    assert current.overdue(datetime(2011, 12, 30, 10, tzinfo=UTC))
    completed, _ = apply(current, "status", status="completed")
    assert not completed.overdue(datetime.now(UTC))
    archived, _ = apply(current, "archive")
    assert not archived.overdue(datetime.now(UTC))


def test_timed_strictly_overdue():
    current = item(due={"kind": "datetime", "at": "2026-01-01T12:00:00Z", "timezone": "UTC"})
    assert not current.overdue(datetime(2026, 1, 1, 12, tzinfo=UTC))
    assert current.overdue(datetime(2026, 1, 1, 12, 0, 0, 1, tzinfo=UTC))


def test_edit_move_event_order_and_no_business_text_snapshot():
    old, new = uuid4(), uuid4()
    current = item(business_context_id=old)
    updated, events = apply(
        current,
        "edit",
        edit={
            "title": "Private new title",
            "description": "private description",
            "business_context_id": new,
            "due": {"kind": "date", "date": "2030-01-01", "timezone": "UTC"},
        },
    )
    assert updated.version == 2
    assert [e.event_type.value for e in events] == [
        "edited",
        "context_disassociated",
        "context_associated",
    ]
    assert [e.context_at_event_id for e in events] == [old, old, new]
    assert [e.event_ordinal for e in events] == [0, 1, 2]
    assert len({e.occurred_at for e in events}) == 1
    assert all(e.item_version == 2 for e in events)
    assert "Private" not in str(events) and "private description" not in str(events)


@pytest.mark.parametrize("key", ["", "x" * 129, "á", "space key", "a/b", "a\n", "a\\b"])
def test_bad_creation_keys(key):
    with pytest.raises(ValueError):
        validate_creation_key(key)


def test_canonical_defaults_source_order_and_provider_case():
    source = WorkItemSource(
        source_kind="communication", connector_account_id=uuid4(), provider_message_id=" Case "
    )
    other = source.model_copy(update={"provider_message_id": " case "})
    assert source_key(source) != source_key(other)
    a = CreationIntent(kind="action", title=" Title ", description=" ", sources=(source, other))
    b = CreationIntent(
        kind="action",
        title="Title",
        description=None,
        due={"kind": "none"},
        business_context_id=None,
        sources=(other, source),
    )
    assert a.request_hash() == b.request_hash()
    assert a.request_hash() != b.model_copy(update={"title": "title"}).request_hash()
    assert validate_creation_key("aA09._~-") == "aA09._~-"


@pytest.mark.parametrize("count", [10, 11])
def test_source_count(count):
    sources = tuple(
        WorkItemSource(source_kind="communication_analysis", analysis_id=uuid4())
        for _ in range(count)
    )
    if count == 11:
        with pytest.raises(ValidationError):
            CreationIntent(kind="action", title="Title", sources=sources)
    else:
        assert len(CreationIntent(kind="action", title="Title", sources=sources).sources) == 10


def test_source_duplicates_and_origin_required():
    source = WorkItemSource(
        source_kind="communication_analysis",
        analysis_id=uuid4(),
        candidate_field="action_items",
        candidate_index=0,
        candidate_digest="a" * 64,
    )
    with pytest.raises(ValidationError):
        CreationIntent(kind="action", title="Title", sources=(source, source))
    locator = source.locator()
    assert isinstance(locator, CandidateLocator)
    with pytest.raises(ValidationError):
        CreationIntent(
            kind="action",
            title="Title",
            creation_origin="ai_confirmed",
            origin_candidate=locator,
            confirmed=True,
        )
    current, _ = BusinessWorkItem.create(
        uuid4(),
        "key",
        CreationIntent(
            kind="action",
            title="Title",
            creation_origin="ai_confirmed",
            origin_candidate=locator,
            confirmed=True,
            sources=(source,),
        ),
    )
    assert current.confirmed_by_user_id == current.owner_user_id
    assert current.confirmed_at == current.created_at


@pytest.mark.parametrize(
    "data",
    [
        {"source_kind": "communication"},
        {
            "source_kind": "communication_analysis",
            "analysis_id": uuid4(),
            "attachment_analysis_id": uuid4(),
        },
        {
            "source_kind": "communication_analysis",
            "analysis_id": uuid4(),
            "candidate_field": "action_items",
        },
        {"source_kind": "attachment_analysis", "attachment_analysis_id": uuid4()},
        {
            "source_kind": "communication",
            "connector_account_id": uuid4(),
            "provider_message_id": "\t\n",
        },
        {
            "source_kind": "communication_analysis",
            "analysis_id": uuid4(),
            "candidate_field": "potential_dates",
            "candidate_index": 0,
            "candidate_digest": "a" * 64,
        },
    ],
)
def test_source_shapes(data):
    with pytest.raises(ValidationError):
        WorkItemSource.model_validate(data)


def test_event_rejects_arbitrary_metadata_actor_and_size():
    current, (event,) = BusinessWorkItem.create(
        uuid4(), "key", CreationIntent(kind="action", title="Title")
    )
    data = event.model_dump()
    for changes in (
        {"actor_user_id": uuid4()},
        {"metadata": {"old_title": "secret"}},
        {"metadata": {"status": "completed", "due": {"kind": "none"}, "creation_origin": "manual"}},
    ):
        with pytest.raises(ValidationError):
            WorkItemEvent.model_validate(data | changes)
    with pytest.raises(ValidationError):
        WorkItemEvent.model_validate(
            data | {"event_type": "edited", "metadata": {"changed_fields": ["title"] * 9000}}
        )


def test_candidate_digest_exact_optional_values_and_locator_identity():
    import hashlib

    from app.domain.models.work_item_intent import candidate_digest, origin_candidate_key

    value = {"description": "Review", "owner": None, "due_at": None, "priority": None}
    expected = hashlib.sha256(
        b'{"description":"Review","due_at":null,"owner":null,"priority":null}'
    ).hexdigest()
    assert candidate_digest(value) == expected
    assert candidate_digest({"description": "Review"}) != expected
    assert candidate_digest("Review") != candidate_digest("review")
    locator = CandidateLocator(
        source_kind="communication_analysis",
        source_id=uuid4(),
        field="action_items",
        index=0,
        digest=expected,
    )
    assert origin_candidate_key(locator) == origin_candidate_key(
        CandidateLocator.model_validate_json(locator.model_dump_json())
    )
    assert origin_candidate_key(locator) != origin_candidate_key(
        locator.model_copy(update={"source_id": uuid4()})
    )
    with pytest.raises(ValidationError):
        candidate_digest({"description": "Review", "raw_body": "Forbidden"})
    with pytest.raises(ValidationError):
        origin_candidate_key(locator.model_copy(update={"digest": "invalid"}))
    with pytest.raises(ValueError):
        candidate_digest(float("nan"))


@pytest.mark.parametrize("zone", ["localtime", "posixrules", "right/UTC", "posix/UTC", "UTC" * 22])
def test_non_iana_or_overlong_zone_rejected(zone):
    with pytest.raises(ValidationError):
        DUE_ADAPTER.validate_python({"kind": "date", "date": "2026-01-01", "timezone": zone})


@pytest.mark.parametrize(
    "field,value",
    [("title", ""), ("title", "a" * 201), ("description", "a" * 4001), ("confirmed", "true")],
)
def test_creation_limits_and_strict_confirmation(field, value):
    with pytest.raises(ValidationError):
        CreationIntent.model_validate({"kind": "action", "title": "Valid", field: value})


def test_due_change_hash_keeps_confirmed_zone_and_calendar_identity():
    first = CreationIntent(
        kind="action",
        title="Title",
        due={"kind": "datetime", "at": "2026-01-01T12:00:00Z", "timezone": "UTC"},
    )
    same = CreationIntent(
        kind="action",
        title="Title",
        due={"kind": "datetime", "at": "2026-01-01T12:00:00.000000+00:00", "timezone": "UTC"},
    )
    other_zone = CreationIntent(
        kind="action",
        title="Title",
        due={"kind": "datetime", "at": "2026-01-01T12:00:00Z", "timezone": "Europe/London"},
    )
    assert first.request_hash() == same.request_hash()
    assert first.request_hash() != other_zone.request_hash()
    assert (
        first.request_hash()
        != CreationIntent(
            kind="action",
            title="Title",
            due={"kind": "date", "date": "2026-01-01", "timezone": "UTC"},
        ).request_hash()
    )
