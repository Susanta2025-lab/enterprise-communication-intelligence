"""Persisted metadata only. No provider, parser, credential or execution ports."""

from uuid import UUID

from app.domain.exceptions import WorkItemConflictError, WorkItemInputError, WorkItemNotFoundError
from app.domain.models.business_work_item_source import CandidateLocator, WorkItemSource
from app.domain.models.work_item_intent import candidate_digest
from app.domain.models.work_item_provenance import WorkItemCandidate, WorkItemSourceDetail


def analysis_record(uow, owner, kind, source_id):
    repository = (
        uow.analysis_repository if kind == "communication_analysis" else uow.attachment_analyses
    )
    row = repository.get_by_id_for_user(source_id, owner)
    if row is None:
        raise WorkItemNotFoundError()
    return row


def observations(row, kind):
    if kind == "attachment_analysis" and row.kind == "xlsx":
        result = row.tabular_result
        return (
            {
                "potential_action_mentions": result.potential_action_mentions,
                "potential_dates": result.potential_dates,
            }
            if result
            else {"potential_action_mentions": [], "potential_dates": []}
        )
    return {"action_items": row.action_items}


def validate_candidate(row, locator):
    fields = observations(row, locator.source_kind)
    if locator.field not in fields or locator.index >= len(fields[locator.field]):
        raise WorkItemInputError()
    try:
        digest = candidate_digest(fields[locator.field][locator.index], field=locator.field)
    except ValueError:
        raise WorkItemConflictError("work_item_candidate_changed") from None
    if digest != locator.digest:
        raise WorkItemConflictError("work_item_candidate_changed")


def project(row, kind, *, limit, offset):
    """Independent arrays, stable field order, original values and disclosures."""
    tabular = getattr(row, "tabular_result", None)
    disclosures = dict(
        truncated=getattr(row, "truncated", False) or bool(tabular and tabular.source_truncated),
        warnings=tuple(getattr(row, "warnings", ())) + (tuple(tabular.warnings) if tabular else ()),
        limitations=tuple(tabular.limitations) if tabular else (),
    )
    result = []
    for field, values in observations(row, kind).items():
        if offset >= len(values):
            offset -= len(values)
            continue
        end = min(len(values), offset + limit - len(result))
        for index in range(offset, end):
            value = values[index]
            try:
                digest = candidate_digest(value, field=field)
            except ValueError:
                # Persisted malformed observations cannot be confirmed.
                raise WorkItemConflictError("work_item_candidate_changed") from None
            result.append(
                WorkItemCandidate(
                    candidate=CandidateLocator(
                        source_kind=kind,
                        source_id=row.id,
                        field=field,
                        index=index,
                        digest=digest,
                    ),
                    value=value,
                    **disclosures,
                )
            )
        if len(result) == limit:
            break
        offset = 0
    return result


def verify_reference(uow, owner, reference):
    values = reference.source_values()
    if reference.source_kind != "communication":
        row = analysis_record(uow, owner, reference.source_kind, reference.source_id)
        if reference.candidate:
            validate_candidate(row, reference.candidate)
        values["connector_account_id"] = row.connector_account_id
        if reference.source_kind == "communication_analysis":
            values["provider_message_id"] = row.message_id if row.connector_account_id else None
        else:
            values["provider_message_id"] = row.provider_message_id
            values["provider_attachment_id"] = row.provider_attachment_id
    if (
        values["connector_account_id"]
        and uow.connector_accounts.get_owned(UUID(str(values["connector_account_id"])), owner)
        is None
    ):
        raise WorkItemNotFoundError()
    try:
        return WorkItemSource(**values)
    except ValueError:
        raise WorkItemNotFoundError() from None


def source_detail(uow, owner, source):
    available = True
    if source.connector_account_id:
        available = uow.connector_accounts.get_owned(source.connector_account_id, owner) is not None
    if source.source_kind != "communication":
        try:
            analysis_record(
                uow, owner, source.source_kind, source.analysis_id or source.attachment_analysis_id
            )
        except WorkItemNotFoundError:
            available = False
    return WorkItemSourceDetail(
        **source.model_dump(exclude={"candidate_digest"}),
        availability="available" if available else "unavailable",
    )
