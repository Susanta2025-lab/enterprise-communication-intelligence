"""Approval-gated workflow action use cases.

Create snapshots a usable ``DraftReply.body`` from an owned analysis. Approve
and reject operate on the persisted ``WorkflowAction`` only; they do not reload
the analysis or call an AI provider.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any
from uuid import UUID

from app.application.exceptions import (
    AnalysisHasNoDraftReplyError,
    AnalysisNotFoundError,
    WorkflowActionConflictError,
    WorkflowActionNotFoundError,
)
from app.application.services.identity import IdentityResolver
from app.core.exceptions import PersistenceError, ServiceUnavailableError
from app.core.logging import get_logger
from app.core.security import AuthenticatedPrincipal
from app.core.telemetry import elapsed_ms, error_class
from app.domain.enums import WorkflowActionStatus, WorkflowActionType
from app.domain.interfaces.persistence_unit_of_work import PersistenceUnitOfWork
from app.domain.interfaces.workflow_action_repository import (
    WorkflowActionSaveOutcome,
    WorkflowActionSaveResult,
)
from app.domain.models.validation import require_non_empty_text
from app.domain.models.workflow import WorkflowAction

logger = get_logger(__name__)

_UNAVAILABLE = "Persistence is currently unavailable."
_DEFAULT_LIST_LIMIT = 20
_MAX_LIST_LIMIT = 100


class WorkflowActionService:
    """Create, retrieve, list, approve, and reject user-owned workflow actions."""

    def __init__(
        self,
        identity_resolver: IdentityResolver,
        unit_of_work_factory: Callable[[], PersistenceUnitOfWork],
    ) -> None:
        self._identity_resolver = identity_resolver
        self._unit_of_work_factory = unit_of_work_factory

    def create(
        self,
        principal: AuthenticatedPrincipal,
        analysis_id: UUID,
    ) -> WorkflowAction:
        """Snapshot an owned analysis draft reply into a PENDING workflow action."""
        started_at = time.perf_counter()
        user_id = self._identity_resolver.find_existing(principal)
        if user_id is None:
            raise AnalysisNotFoundError()
        try:
            with self._unit_of_work_factory() as uow:
                analysis = uow.analysis_repository.get_by_id_for_user(analysis_id, user_id)
                if analysis is None:
                    raise AnalysisNotFoundError()
                proposed = _usable_draft_body(analysis.draft_reply)
                action = WorkflowAction(
                    action_type=WorkflowActionType.REPLY,
                    analysis_id=analysis.id,
                    owner_user_id=user_id,
                    proposed_reply_body=proposed,
                )
                stored = uow.workflow_actions.add(action)
                uow.commit()
        except AnalysisNotFoundError:
            raise
        except AnalysisHasNoDraftReplyError:
            raise
        except PersistenceError as exc:
            logger.warning(
                "workflow_action_persistence_failed",
                operation="create",
                analysis_id=str(analysis_id),
                duration_ms=elapsed_ms(started_at),
                error_class=error_class(exc),
            )
            raise ServiceUnavailableError(_UNAVAILABLE) from None

        logger.info(
            "workflow_action_created",
            operation="create",
            workflow_action_id=str(stored.id),
            analysis_id=str(analysis_id),
            duration_ms=elapsed_ms(started_at),
        )
        return stored

    def get(
        self,
        principal: AuthenticatedPrincipal,
        action_id: UUID,
    ) -> WorkflowAction:
        """Return an owned workflow action or raise not-found."""
        started_at = time.perf_counter()
        user_id = self._require_existing_user(principal)
        try:
            with self._unit_of_work_factory() as uow:
                action = uow.workflow_actions.get_owned(action_id, user_id)
        except PersistenceError as exc:
            logger.warning(
                "workflow_action_persistence_failed",
                operation="get",
                workflow_action_id=str(action_id),
                duration_ms=elapsed_ms(started_at),
                error_class=error_class(exc),
            )
            raise ServiceUnavailableError(_UNAVAILABLE) from None

        if action is None:
            raise WorkflowActionNotFoundError()

        logger.info(
            "workflow_action_retrieved",
            operation="get",
            workflow_action_id=str(action.id),
            duration_ms=elapsed_ms(started_at),
        )
        return action

    def list(
        self,
        principal: AuthenticatedPrincipal,
        limit: int = _DEFAULT_LIST_LIMIT,
        offset: int = 0,
    ) -> list[WorkflowAction]:
        """Return a bounded page of workflow actions owned by the principal."""
        started_at = time.perf_counter()
        user_id = self._identity_resolver.find_existing(principal)
        if user_id is None:
            logger.info(
                "workflow_actions_listed",
                operation="list",
                result_count=0,
                duration_ms=elapsed_ms(started_at),
            )
            return []
        page_limit = min(limit, _MAX_LIST_LIMIT) if limit >= 1 else limit
        try:
            with self._unit_of_work_factory() as uow:
                actions = uow.workflow_actions.list_owned(user_id, page_limit, offset)
        except PersistenceError as exc:
            logger.warning(
                "workflow_action_persistence_failed",
                operation="list",
                duration_ms=elapsed_ms(started_at),
                error_class=error_class(exc),
            )
            raise ServiceUnavailableError(_UNAVAILABLE) from None

        logger.info(
            "workflow_actions_listed",
            operation="list",
            result_count=len(actions),
            duration_ms=elapsed_ms(started_at),
        )
        return actions

    def approve(
        self,
        principal: AuthenticatedPrincipal,
        action_id: UUID,
    ) -> WorkflowAction:
        """Approve a PENDING owned action by copying the proposed reply snapshot."""
        started_at = time.perf_counter()
        saved = self._transition_pending(
            principal,
            action_id,
            operation="approve",
            apply=lambda action: action.approve(),
        )
        logger.info(
            "workflow_action_approved",
            operation="approve",
            workflow_action_id=str(saved.id),
            duration_ms=elapsed_ms(started_at),
        )
        return saved

    def reject(
        self,
        principal: AuthenticatedPrincipal,
        action_id: UUID,
    ) -> WorkflowAction:
        """Reject a PENDING owned action without depending on the source analysis."""
        started_at = time.perf_counter()
        saved = self._transition_pending(
            principal,
            action_id,
            operation="reject",
            apply=lambda action: action.reject(),
        )
        logger.info(
            "workflow_action_rejected",
            operation="reject",
            workflow_action_id=str(saved.id),
            duration_ms=elapsed_ms(started_at),
        )
        return saved

    def _transition_pending(
        self,
        principal: AuthenticatedPrincipal,
        action_id: UUID,
        *,
        operation: str,
        apply: Callable[[WorkflowAction], None],
    ) -> WorkflowAction:
        started_at = time.perf_counter()
        user_id = self._require_existing_user(principal)
        try:
            with self._unit_of_work_factory() as uow:
                action = uow.workflow_actions.get_owned(action_id, user_id)
                if action is None:
                    raise WorkflowActionNotFoundError()
                apply(action)
                result = uow.workflow_actions.save_owned(
                    action,
                    expected_status=WorkflowActionStatus.PENDING,
                )
                saved = _require_save_success(result)
                uow.commit()
        except WorkflowActionNotFoundError:
            raise
        except WorkflowActionConflictError:
            raise
        except PersistenceError as exc:
            logger.warning(
                "workflow_action_persistence_failed",
                operation=operation,
                workflow_action_id=str(action_id),
                duration_ms=elapsed_ms(started_at),
                error_class=error_class(exc),
            )
            raise ServiceUnavailableError(_UNAVAILABLE) from None
        return saved

    def _require_existing_user(self, principal: AuthenticatedPrincipal) -> UUID:
        user_id = self._identity_resolver.find_existing(principal)
        if user_id is None:
            raise WorkflowActionNotFoundError()
        return user_id


def _require_save_success(result: WorkflowActionSaveResult) -> WorkflowAction:
    if result.outcome is WorkflowActionSaveOutcome.SUCCESS and result.action is not None:
        return result.action
    if result.outcome is WorkflowActionSaveOutcome.NOT_FOUND:
        raise WorkflowActionNotFoundError()
    if result.outcome is WorkflowActionSaveOutcome.CONFLICT:
        raise WorkflowActionConflictError()
    raise PersistenceError("Could not persist workflow action.")


def _usable_draft_body(draft_reply: dict[str, Any] | None) -> str:
    if not isinstance(draft_reply, dict):
        raise AnalysisHasNoDraftReplyError()
    body = draft_reply.get("body")
    if not isinstance(body, str):
        raise AnalysisHasNoDraftReplyError()
    try:
        return require_non_empty_text(body, "proposed_reply_body")
    except ValueError:
        raise AnalysisHasNoDraftReplyError() from None
