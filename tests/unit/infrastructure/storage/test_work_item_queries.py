"""Portable SQL filtering parity, timezone boundaries and bounded pages."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import event, update

from app.domain.exceptions import WorkItemNotFoundError
from app.domain.models.business_work_item import WorkItemCommand
from app.domain.models.work_item_query import WorkItemQuery
from app.infrastructure.storage.models import BusinessWorkItemRow
from app.infrastructure.storage.repositories.business_work_item import (
    SqlAlchemyBusinessWorkItemRepository,
)
from tests.unit.infrastructure.storage.test_business_work_item_repository import (
    context,
    intent,
    owners,
)


@pytest.mark.parametrize(
    "instant",
    [
        "2026-03-29T00:59:59+00:00",
        "2026-03-29T01:00:00+00:00",
        "2026-11-01T05:30:00+00:00",
        "2026-11-01T06:30:00+00:00",
        "2011-12-30T10:00:00+00:00",
        "2026-10-03T15:30:00+00:00",
    ],
)
def test_per_zone_overdue_parity_before_pagination(session_factory, instant):
    owner, foreign = owners(session_factory)
    now = datetime.fromisoformat(instant)
    items = []
    with session_factory() as session:
        repo = SqlAlchemyBusinessWorkItemRepository(session)
        for i, zone in enumerate(
            (
                "Pacific/Kiritimati",
                "Pacific/Honolulu",
                "Pacific/Apia",
                "Europe/London",
                "America/New_York",
                "Australia/Lord_Howe",
            )
        ):
            for day in (now.date().isoformat(), "2000-01-01", "2099-01-01"):
                item = repo.create_owned(
                    owner,
                    f"k{i}-{day}",
                    intent(
                        due={
                            "kind": "date",
                            "date": day,
                            "timezone": zone,
                        }
                    ),
                ).item
                items.append(item)
        for i, due in enumerate(
            (
                {"kind": "none"},
                {"kind": "datetime", "at": now, "timezone": "UTC"},
                {"kind": "datetime", "at": "2000-01-01T00:00:00Z", "timezone": "UTC"},
            )
        ):
            items.append(repo.create_owned(owner, f"t{i}", intent(due=due)).item)
        for status in ("completed", "cancelled"):
            item = repo.create_owned(
                owner, status, intent(due={"kind": "date", "date": "2000-01-01", "timezone": "UTC"})
            ).item
            items.append(
                repo.mutate_owned(
                    item.id,
                    owner,
                    WorkItemCommand(operation="status", expected_version=1, status=status),
                )
            )
        item = repo.create_owned(
            owner, "archived", intent(due={"kind": "date", "date": "2000-01-01", "timezone": "UTC"})
        ).item
        items.append(
            repo.mutate_owned(
                item.id, owner, WorkItemCommand(operation="archive", expected_version=1)
            )
        )
        repo.create_owned(foreign, "foreign", intent())
        session.commit()
    with session_factory() as session:
        repo = SqlAlchemyBusinessWorkItemRepository(session)
        for overdue in (True, False):
            expected = sorted(
                (i for i in items if i.overdue(now) == overdue),
                key=lambda i: (i.created_at, i.id),
                reverse=True,
            )
            pages = [
                repo.list_owned(
                    owner,
                    WorkItemQuery(overdue=overdue, archive="all", limit=3, offset=offset),
                    now,
                )
                for offset in range(0, len(expected) + 3, 3)
            ]
            actual = [i.id for page in pages for i in page]
            assert actual == [i.id for i in expected]


@pytest.mark.parametrize("lower", ["2026-01-02T00:00:00Z", "2026-01-02T02:00:00+02:00"])
def test_typed_ranges_context_filters_and_tie_breakers(session_factory, lower):
    owner, foreign = owners(session_factory)
    now = datetime.now(UTC)
    with session_factory() as session:
        a, b = context(session, owner), context(session, foreign)
        repo = SqlAlchemyBusinessWorkItemRepository(session)
        items = [
            repo.create_owned(
                owner,
                str(i),
                intent(
                    due={"kind": "date", "date": f"2026-01-0{i + 1}", "timezone": "UTC"},
                    business_context_id=a.id if i < 2 else None,
                ),
            ).item
            for i in range(3)
        ]
        timed = repo.create_owned(
            owner,
            "timed",
            intent(
                due={
                    "kind": "datetime",
                    "at": "2026-01-02T02:00:00+02:00",
                    "timezone": "Europe/Helsinki",
                }
            ),
        ).item
        session.execute(update(BusinessWorkItemRow).values(created_at=now, updated_at=now))
        session.commit()
    with session_factory() as session:
        repo = SqlAlchemyBusinessWorkItemRepository(session)
        assert [i.id for i in repo.list_owned(owner, WorkItemQuery(), now)] == sorted(
            [i.id for i in items] + [timed.id], reverse=True
        )
        assert [
            i.id
            for i in repo.list_owned(
                owner, WorkItemQuery(due_date_from="2026-01-02", due_date_to="2026-01-02"), now
            )
        ] == [items[1].id]
        assert [
            i.id
            for i in repo.list_owned(owner, WorkItemQuery(due_kind="date", sort="due_asc"), now)
        ] == [i.id for i in items]
        assert len(repo.list_owned(owner, WorkItemQuery(business_context_id=a.id), now)) == 2
        assert len(repo.list_owned(owner, WorkItemQuery(unassociated=True), now)) == 2
        assert repo.list_owned(owner, WorkItemQuery(kind="obligation"), now) == ()
        assert repo.list_owned(owner, WorkItemQuery(status="cancelled"), now) == ()
        assert repo.list_owned(owner, WorkItemQuery(archive="archived"), now) == ()
        assert [
            i.id
            for i in repo.list_owned(
                owner,
                WorkItemQuery(
                    due_kind="datetime",
                    sort="due_asc",
                    due_at_from=lower,
                    due_at_to="2026-01-02T00:00:00Z",
                ),
                now,
            )
        ] == [timed.id]
        with pytest.raises(WorkItemNotFoundError):
            repo.list_owned(owner, WorkItemQuery(business_context_id=b.id), now)


def test_bounded_sql_page_and_no_count_query(session_factory):
    owner, _ = owners(session_factory)
    statements = []
    with session_factory() as session:
        repo = SqlAlchemyBusinessWorkItemRepository(session)
        for i in range(12):
            repo.create_owned(owner, str(i), intent())
        session.commit()
    engine = session_factory.kw["bind"]

    def capture(conn, cursor, statement, parameters, context, executemany):
        if statement.lower().startswith("select"):
            statements.append(statement.lower())

    event.listen(engine, "before_cursor_execute", capture)
    try:
        with session_factory() as session:
            result = SqlAlchemyBusinessWorkItemRepository(session).list_owned(
                owner, WorkItemQuery(limit=2, offset=3), datetime.now(UTC)
            )
        assert len(result) == 2 and len(statements) == 1
        assert "limit" in statements[0] and "offset" in statements[0]
        assert "count(" not in statements[0] and "user_id =" in statements[0]
    finally:
        event.remove(engine, "before_cursor_execute", capture)
