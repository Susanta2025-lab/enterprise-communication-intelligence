"""Guarded PostgreSQL conversion and concurrency evidence."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from app.domain.exceptions import WorkItemConflictError
from app.infrastructure.storage.repositories.business_work_item import (
    SqlAlchemyBusinessWorkItemRepository,
)
from tests.unit.infrastructure.storage import test_work_item_conversion as contract
from tests.unit.infrastructure.storage.test_business_work_item_repository import counts

test_service_retention_confirmation_and_erasure = (
    contract.test_service_retention_confirmation_and_erasure
)
test_conversion_failure_atomic = contract.test_conversion_failure_atomic


@pytest.mark.parametrize("mode", ["same_key", "candidate", "changed_intent"])
def test_parallel_verified_confirmation(session_factory, monkeypatch, mode):
    service, principal, request, _ = contract.setup_conversion(session_factory)
    barrier = Barrier(2)
    original = SqlAlchemyBusinessWorkItemRepository._existing_creation

    def synchronized(self, *args):
        result = original(self, *args)
        # Force both requests past the final absence check, so the loser
        # actually encounters SQL uniqueness and savepoint recovery.
        if not getattr(self, "_conversion_race_checked", False):
            self._conversion_race_checked = True
            barrier.wait(timeout=10)
        return result

    monkeypatch.setattr(
        SqlAlchemyBusinessWorkItemRepository, "_existing_creation", synchronized
    )

    def attempt(index):
        changes = {}
        if index:
            if mode == "candidate":
                changes["creation_key"] = "another"
            elif mode == "changed_intent":
                changes["title"] = "Changed"
        try:
            result = service.create_verified(principal, request.model_copy(update=changes))
            return "replayed" if result.replayed else "created"
        except WorkItemConflictError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, range(2)))
    assert results.count("created") == 1
    expected = {
        "same_key": "replayed",
        "candidate": "work_item_candidate_already_tracked",
        "changed_intent": "work_item_creation_key_conflict",
    }[mode]
    assert results.count(expected) == 1
    with session_factory() as session:
        assert counts(session) == (1, 1, 1)
