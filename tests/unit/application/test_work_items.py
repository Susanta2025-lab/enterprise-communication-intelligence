"""Application boundary and persistence error translation."""

from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.application.services.work_items import WorkItemService
from app.core.exceptions import PersistenceError, ServiceUnavailableError
from app.domain.exceptions import WorkItemNotFoundError
from app.domain.models.business_work_item import WorkItemCommand
from app.domain.models.work_item_intent import CreationIntent
from app.domain.models.work_item_query import WorkItemQuery


def test_source_free_application_boundary():
    identity, factory = Mock(), Mock()
    service = WorkItemService(identity, factory)
    intent = CreationIntent(
        kind="action",
        title="x",
        sources=[
            {
                "source_kind": "communication_analysis",
                "analysis_id": uuid4(),
            }
        ],
    )
    with pytest.raises(ValueError, match="source-free"):
        service.create(Mock(), "key", intent)
    identity.resolve_or_create.assert_not_called()
    factory.assert_not_called()


@pytest.mark.parametrize("operation", ["get", "events", "mutate", "list_context"])
def test_unmapped_objects_do_not_access_repository(operation):
    identity, factory = Mock(), Mock()
    identity.find_existing.return_value = None
    service = WorkItemService(identity, factory)
    with pytest.raises(WorkItemNotFoundError):
        if operation == "list_context":
            service.list(Mock(), WorkItemQuery(business_context_id=uuid4()), datetime.now(UTC))
        elif operation == "mutate":
            service.mutate(
                Mock(), uuid4(), WorkItemCommand(operation="archive", expected_version=1)
            )
        else:
            getattr(service, operation)(Mock(), uuid4())
    factory.assert_not_called()


@pytest.mark.parametrize("operation", ["get", "events", "list", "mutate", "create"])
def test_persistence_construction_failure_sanitized(operation):
    identity, factory = Mock(), Mock(side_effect=PersistenceError("secret SQL"))
    identity.find_existing.return_value = uuid4()
    service = WorkItemService(identity, factory)
    with pytest.raises(ServiceUnavailableError, match="Persistence is currently unavailable"):
        if operation == "create":
            service.create(Mock(), "key", CreationIntent(kind="action", title="x"))
        elif operation == "list":
            service.list(Mock(), WorkItemQuery(), datetime.now(UTC))
        elif operation == "mutate":
            service.mutate(
                Mock(), uuid4(), WorkItemCommand(operation="archive", expected_version=1)
            )
        else:
            getattr(service, operation)(Mock(), uuid4())
