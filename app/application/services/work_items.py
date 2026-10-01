"""Owned tracking use cases; no provider or execution dependencies."""

from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from app.application.services.identity import IdentityResolver
from app.application.services.work_item_provenance import (
    analysis_record,
    project,
    source_detail,
    verify_reference,
)
from app.core.exceptions import PersistenceError, ServiceUnavailableError
from app.core.security import AuthenticatedPrincipal
from app.domain.exceptions import (
    WorkItemConflictError,
    WorkItemNotFoundError,
    WorkItemPermissionError,
)
from app.domain.interfaces.business_work_item_repository import WorkItemCreationResult
from app.domain.interfaces.persistence_unit_of_work import PersistenceUnitOfWork
from app.domain.models.business_work_item import WorkItemCommand
from app.domain.models.work_item_intent import CreationIntent
from app.domain.models.work_item_query import WorkItemQuery


class WorkItemService:
    def __init__(
        self,
        identity_resolver: IdentityResolver,
        unit_of_work_factory: Callable[[], PersistenceUnitOfWork],
    ):
        self._identity = identity_resolver
        self._factory = unit_of_work_factory

    def _run(self, operation, *, write=False):
        try:
            with self._factory() as uow:
                result = operation(uow.business_work_items)
                if write:
                    uow.commit()
                return result
        except PersistenceError:
            raise ServiceUnavailableError("Persistence is currently unavailable.") from None

    def _owner(self, principal):
        owner = self._identity.find_existing(principal)
        if owner is None:
            raise WorkItemNotFoundError()
        return owner

    def create(self, principal: AuthenticatedPrincipal, creation_key: str, intent: CreationIntent):
        # Legacy source-free convenience entry; provenance uses create_verified.
        if intent.sources or intent.creation_origin != "manual":
            raise ValueError("only source-free manual creation is supported")
        owner = self._identity.resolve_or_create(principal)
        return self._run(lambda repo: repo.create_owned(owner, creation_key, intent), write=True)

    @staticmethod
    def _require_source_permission(principal, sources):
        if (
            any(s.connector_account_id is not None for s in sources)
            and "communications:read" not in principal.permissions
        ):
            raise WorkItemPermissionError()

    def create_verified(self, principal, request):
        request = type(request).model_validate(request.model_dump())
        owner = self._identity.resolve_or_create(principal)
        try:
            with self._factory() as uow:
                repo = uow.business_work_items
                existing = repo.get_by_creation_key_owned(owner, request.creation_key)
                if existing is not None:
                    self._require_source_permission(
                        principal, repo.sources_owned(existing.id, owner)
                    )
                    if existing.creation_request_hash != request.request_hash():
                        raise WorkItemConflictError("work_item_creation_key_conflict")
                    return WorkItemCreationResult(existing, replayed=True)
                sources = tuple(verify_reference(uow, owner, ref) for ref in request.references())
                self._require_source_permission(principal, sources)
                candidate = getattr(request, "candidate", None)
                intent = CreationIntent(
                    **request.model_dump(
                        exclude={"creation_key", "sources", "candidate", "confirmed"}
                    ),
                    sources=sources,
                    origin_candidate=candidate.model_dump() if candidate is not None else None,
                    confirmed=candidate is not None,
                    creation_origin="ai_confirmed" if candidate is not None else "manual",
                )
                result = repo.create_owned(owner, request.creation_key, intent)
                # Concurrent replay must also use the winner's immutable provenance.
                self._require_source_permission(
                    principal, repo.sources_owned(result.item.id, owner)
                )
                uow.commit()
                return result
        except PersistenceError:
            raise ServiceUnavailableError("Persistence is currently unavailable.") from None

    def candidates(self, principal, query):
        owner = self._owner(principal)
        try:
            with self._factory() as uow:
                row = analysis_record(uow, owner, query.source_kind, query.source_id)
                return project(row, query.source_kind, limit=query.limit, offset=query.offset)
        except PersistenceError:
            raise ServiceUnavailableError("Persistence is currently unavailable.") from None

    def detail(self, principal, item_id):
        owner = self._owner(principal)
        try:
            with self._factory() as uow:
                item = uow.business_work_items.get_owned(item_id, owner)
                if item is None:
                    raise WorkItemNotFoundError()
                sources = tuple(
                    source_detail(uow, owner, source)
                    for source in uow.business_work_items.sources_owned(item_id, owner)
                )
                return item, sources
        except PersistenceError:
            raise ServiceUnavailableError("Persistence is currently unavailable.") from None

    def get(self, principal: AuthenticatedPrincipal, item_id: UUID):
        owner = self._owner(principal)
        item = self._run(lambda repo: repo.get_owned(item_id, owner))
        if item is None:
            raise WorkItemNotFoundError()
        return item

    def list(self, principal: AuthenticatedPrincipal, query: WorkItemQuery, now: datetime):
        owner = self._identity.find_existing(principal)
        if owner is None:
            if query.business_context_id:
                raise WorkItemNotFoundError()
            return ()
        return self._run(lambda repo: repo.list_owned(owner, query, now))

    def mutate(self, principal: AuthenticatedPrincipal, item_id: UUID, command: WorkItemCommand):
        owner = self._owner(principal)
        return self._run(lambda repo: repo.mutate_owned(item_id, owner, command), write=True)

    def events(self, principal: AuthenticatedPrincipal, item_id: UUID, *, limit=20, offset=0):
        owner = self._owner(principal)
        return self._run(lambda repo: repo.events_owned(item_id, owner, limit=limit, offset=offset))
