"""Verified conversion HTTP contracts against local SQL; all side effects forbidden."""

import hashlib
import json
from uuid import uuid4

import pytest
from sqlalchemy import delete, update

from app.application.services.identity import IdentityResolver
from app.core.security import AuthenticatedPrincipal
from app.domain.interfaces.analysis_repository import NewAnalysis
from app.domain.interfaces.attachment_analysis_repository import NewAttachmentAnalysis
from app.domain.interfaces.connector_account_repository import NewConnectorAccount
from app.domain.models.tabular_analysis import TabularAnalysisResult
from app.domain.models.work_item_intent import candidate_digest
from app.infrastructure.storage.models import Analysis, AttachmentAnalysisRow, ConnectorAccount
from tests.integration.test_business_contexts import _analyze_headers, _headers
from tests.integration.test_work_items import URL
from tests.integration.test_work_items import api as _api
from tests.support.jwt_tokens import TEST_ISSUER, TEST_PERMISSION
from tests.unit.infrastructure.storage.test_business_work_item_repository import counts

api = _api


def seed(api, *, kind="text", length=30, subject="user-a-subject", empty=False):
    _, _, _, factory = api
    principal = AuthenticatedPrincipal(TEST_ISSUER, subject, frozenset({TEST_PERMISSION}))
    owner = IdentityResolver(factory).resolve_or_create(principal)
    with factory() as uow:
        account = None
        if kind != "text":
            account = uow.connector_accounts.create(
                NewConnectorAccount(
                    user_id=owner,
                    provider="gmail",
                    external_account_id=str(uuid4()),
                )
            )
        if kind in ("text", "mail"):
            row = uow.analysis_repository.save(
                NewAnalysis(
                    user_id=owner,
                    provider="mock",
                    priority="medium",
                    category="general",
                    source_type="text",
                    summary_text="Advisory",
                    action_items=[]
                    if empty
                    else [{"description": "X" * length, "owner": "advisory"}],
                    connector_account_id=account.id if account else None,
                    message_id="MiXeD opaque " if account else None,
                )
            )
            source_kind = "communication_analysis"
        else:
            tabular = (
                TabularAnalysisResult(
                    summary="Advisory",
                    potential_action_mentions=[] if empty else ["X" * length],
                    potential_dates=[] if empty else ["next quarter"],
                    potential_amounts=["not a candidate"],
                    warnings=["uncertain"],
                    limitations=["sampled"],
                    source_truncated=True,
                )
                if kind == "xlsx"
                else None
            )
            row = uow.attachment_analyses.save(
                NewAttachmentAnalysis(
                    user_id=owner,
                    connector_account_id=account.id,
                    provider_message_id="MiXeD opaque ",
                    provider_attachment_id="Attach-ID",
                    media_type="application/octet-stream",
                    kind=kind,
                    extracted_content_status="truncated_text",
                    truncated=True,
                    warnings=["bounded"],
                    summary_text="Advisory",
                    priority="medium",
                    category="general",
                    action_items=[] if empty else [{"description": "X" * length}],
                    provider="mock",
                    tabular_result=tabular,
                )
            )
            source_kind = "attachment_analysis"
        uow.commit()
    return owner, row.id, source_kind, account.id if account else None


def candidates(api, source, **query):
    client, key, *_ = api
    return client.get(
        URL + "/candidates",
        params={
            "source_kind": source[2],
            "source_id": str(source[1]),
            **query,
        },
        headers=_analyze_headers(key),
    )


def body_for(api, source):
    response = candidates(api, source)
    assert response.status_code == 200, response.text
    return dict(
        creation_key="convert",
        kind="action",
        title="Reviewed action",
        due={"kind": "none"},
        confirmed=True,
        candidate=response.json()["items"][0]["candidate"],
    )


def post(api, body, *, read=False, manual=False, subject="user-a-subject"):
    client, key, *_ = api
    permissions = TEST_PERMISSION + (" communications:read" if read else "")
    return client.post(
        URL + ("" if manual else "/from-analysis"),
        json=body,
        headers=_headers(key, subject, permissions),
    )


def assert_counts(api, expected):
    with api[2]() as session:
        assert counts(session) == expected


@pytest.mark.parametrize("kind", ["text", "mail", "pdf", "docx", "txt", "png", "jpeg", "xlsx"])
def test_projection_read_only_and_explicit_conversion(api, kind):
    source = seed(api, kind=kind)
    response = candidates(api, source)
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert len(items) == (2 if kind == "xlsx" else 1)
    assert items[0]["advisory"] is True
    assert_counts(api, (0, 0, 0))
    body = body_for(api, source)
    if kind != "text":
        assert post(api, body).status_code == 403
        assert_counts(api, (0, 0, 0))
    created = post(api, body, read=kind != "text")
    assert created.status_code == 201, created.text
    assert created.json()["creation_origin"] == "ai_confirmed"
    assert created.json()["confirmed_at"] == created.json()["created_at"]
    assert_counts(api, (1, 1, 1))
    assert post(api, body, read=kind != "text").status_code == 200
    assert_counts(api, (1, 1, 1))
    detail = api[0].get(created.headers["location"], headers=_analyze_headers(api[1])).json()
    assert detail["sources"][0]["availability"] == "available"
    assert "candidate_digest" not in detail["sources"][0]
    assert detail["sources"][0]["provider_message_id"] == (
        "MiXeD opaque " if kind != "text" else None
    )
    assert detail["sources"][0]["provider_content_verified"] is False


@pytest.mark.parametrize("length", [200, 201, 300])
def test_long_observation_kept_whole_requires_reviewed_title(api, length):
    source = seed(api, kind="xlsx", length=length)
    value = candidates(api, source).json()["items"][0]
    assert value["value"] == "X" * length
    expected = hashlib.sha256(json.dumps("X" * length).encode()).hexdigest()
    assert value["candidate"]["digest"] == expected
    assert_counts(api, (0, 0, 0))
    body = body_for(api, source)
    if length > 200:
        assert post(api, body | {"title": "X" * length}, read=True).status_code == 422
    assert post(api, body, read=True).status_code == 201
    assert_counts(api, (1, 1, 1))


@pytest.mark.parametrize(
    "field,limit", [("potential_dates", 200), ("potential_action_mentions", 300)]
)
def test_digest_source_bounds(field, limit):
    assert candidate_digest("x" * limit, field=field)
    with pytest.raises(ValueError):
        candidate_digest("x" * (limit + 1), field=field)
    with pytest.raises(ValueError):
        candidate_digest(" ", field=field)


def test_xlsx_independent_observations_disclosures_pagination(api):
    source = seed(api, kind="xlsx")
    items = candidates(api, source).json()["items"]
    assert [v["candidate"]["field"] for v in items] == [
        "potential_action_mentions",
        "potential_dates",
    ]
    assert [v["candidate"]["index"] for v in items] == [0, 0]
    assert all(v["truncated"] and v["warnings"] == ["bounded", "uncertain"] for v in items)
    assert all(v["limitations"] == ["sampled"] for v in items)
    assert candidates(api, source, offset=1, limit=1).json()["items"] == [items[1]]
    body = body_for(api, source) | {"candidate": items[1]["candidate"]}
    assert post(api, body | {"title": ""}, read=True).status_code == 422
    assert post(api, body | {"due": None}, read=True).status_code == 422
    result = post(api, body | {"title": "Review the observed date"}, read=True)
    assert result.status_code == 201 and result.json()["due"] == {"kind": "none"}


@pytest.mark.parametrize("kind", ["text", "pdf", "xlsx"])
def test_empty_projection(api, kind):
    assert candidates(api, seed(api, kind=kind, empty=True)).json()["items"] == []
    assert_counts(api, (0, 0, 0))


@pytest.mark.parametrize(
    "change",
    [
        {"projection_version": 2},
        {"projection_version": True},
        {"projection_version": 1.0},
        {"field": "potential_amounts"},
        {"field": "potential_dates"},
        {"index": -1},
        {"index": True},
        {"index": 999},
        {"digest": "A" * 64},
        {"source_kind": "communication"},
        {"owner_user_id": str(uuid4())},
    ],
)
def test_invalid_locators(api, change):
    body = body_for(api, seed(api))
    body["candidate"].update(change)
    result = post(api, body)
    assert result.status_code == 422, result.text
    assert_counts(api, (0, 0, 0))


@pytest.mark.parametrize(
    "change",
    [
        {"confirmed": False},
        {"confirmed": "true"},
        {"title": "x" * 201},
        {"description": "x" * 4001},
        {"user_id": str(uuid4())},
        {"actor_user_id": str(uuid4())},
        {"owner_user_id": str(uuid4())},
        {"confirmed_by_user_id": str(uuid4())},
        {"confirmed_at": "2026-01-01"},
        {"version": 1},
        {"status": "open"},
        {"workflow_execution_target": {}},
        {"provider_credentials": {}},
    ],
)
def test_confirmation_strict_no_partial_writes(api, change):
    body = body_for(api, seed(api)) | change
    assert post(api, body).status_code == 422
    assert_counts(api, (0, 0, 0))


@pytest.mark.parametrize("field", ["confirmed", "title", "due", "candidate", "creation_key"])
def test_confirmation_required(api, field):
    body = body_for(api, seed(api))
    del body[field]
    assert post(api, body).status_code == 422
    assert_counts(api, (0, 0, 0))


def test_changed_digest_and_changed_value(api):
    source = seed(api)
    body = body_for(api, source)
    tampered = body | {"candidate": body["candidate"] | {"digest": "0" * 64}}
    result = post(api, tampered)
    assert result.status_code == 409 and result.json()["code"] == "work_item_candidate_changed"
    with api[2]() as session:
        session.execute(update(Analysis).values(action_items=[{"description": "changed"}]))
        session.commit()
    assert post(api, body).json()["code"] == "work_item_candidate_changed"
    assert_counts(api, (0, 0, 0))


@pytest.mark.parametrize("kind", ["text", "mail", "pdf", "xlsx"])
def test_replay_conflicts_and_source_deletion(api, kind):
    source = seed(api, kind=kind)
    body = body_for(api, source)
    created = post(api, body, read=True)
    assert created.status_code == 201
    changed = post(api, body | {"title": "Changed"}, read=True)
    assert (
        changed.status_code == 409 and changed.json()["code"] == "work_item_creation_key_conflict"
    )
    duplicate = post(api, body | {"creation_key": "different"}, read=True)
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "work_item_candidate_already_tracked"
    assert duplicate.headers["location"] == created.headers["location"]
    with api[2]() as session:
        session.execute(delete(Analysis if kind in ("text", "mail") else AttachmentAnalysisRow))
        session.execute(delete(ConnectorAccount))
        session.commit()
    assert post(api, body, read=True).status_code == 200
    if kind != "text":
        assert post(api, body).status_code == 403
        assert post(api, body | {"title": "different"}).status_code == 403
    detail = api[0].get(created.headers["location"], headers=_analyze_headers(api[1])).json()
    assert detail["sources"][0]["availability"] == "unavailable"
    assert_counts(api, (1, 1, 1))


@pytest.mark.parametrize("kind", ["text", "pdf"])
def test_unknown_foreign_source_indistinguishable(api, kind):
    source = seed(api, kind=kind)
    body = body_for(api, source)
    foreign = seed(api, kind=kind, subject="foreign")
    body["candidate"]["source_id"] = str(foreign[1])
    result = post(api, body, read=True)
    assert result.status_code == 404
    body["candidate"]["source_id"] = str(uuid4())
    assert post(api, body, read=True).json() == result.json()
    assert candidates(api, foreign).status_code == 404
    assert_counts(api, (0, 0, 0))


def test_manual_sources_bound_duplicates_and_read_gate(api):
    source = seed(api, kind="mail")
    refs = [
        {
            "source_kind": "communication",
            "connector_account_id": str(source[3]),
            "provider_message_id": f"CaseSensitive-{i}",
        }
        for i in range(11)
    ]
    body = dict(creation_key="manual", kind="obligation", title="Reviewed", sources=refs[:10])
    assert post(api, body, manual=True).status_code == 403
    assert post(api, body | {"sources": refs}, manual=True, read=True).status_code == 422
    assert post(api, body | {"sources": refs[:1] * 2}, manual=True, read=True).status_code == 422
    created = post(api, body, manual=True, read=True)
    assert created.status_code == 201, created.text
    assert_counts(api, (1, 10, 1))
    assert (
        post(api, body | {"sources": list(reversed(refs[:10]))}, manual=True, read=True).status_code
        == 200
    )


@pytest.mark.parametrize("kind", ["mail", "pdf"])
def test_nested_sources_require_read_and_derive_tuple(api, kind):
    origin = seed(api)
    extra = seed(api, kind=kind)
    body = body_for(api, origin) | {
        "sources": [{"source_kind": extra[2], "source_id": str(extra[1])}]
    }
    assert post(api, body).status_code == 403
    assert_counts(api, (0, 0, 0))
    spoof = body | {"sources": [body["sources"][0] | {"connector_account_id": str(uuid4())}]}
    assert post(api, spoof, read=True).status_code == 422
    assert post(api, body, read=True).status_code == 201
    assert_counts(api, (1, 2, 1))


def test_additional_origin_duplicate_and_limits(api):
    origin = seed(api)
    body = body_for(api, origin)
    ref = {"source_kind": origin[2], "source_id": str(origin[1]), "candidate": body["candidate"]}
    assert post(api, body | {"sources": [ref]}).status_code == 422
    assert post(api, body | {"sources": [ref] * 10}).status_code == 422
    assert_counts(api, (0, 0, 0))


def test_direct_connector_foreign_and_disconnected(api):
    source = seed(api, kind="mail")
    foreign = seed(api, kind="mail", subject="foreign")
    body = dict(
        creation_key="direct",
        kind="action",
        title="Reviewed",
        sources=[
            {
                "source_kind": "communication",
                "connector_account_id": str(foreign[3]),
                "provider_message_id": "Opaque-MESSAGE",
            }
        ],
    )
    missing = post(api, body, manual=True, read=True)
    assert missing.status_code == 404
    body["sources"][0]["connector_account_id"] = str(uuid4())
    assert post(api, body, manual=True, read=True).json() == missing.json()
    body["sources"][0]["connector_account_id"] = str(source[3])
    with api[3]() as uow:
        uow.connector_accounts.disconnect_owned(source[3], source[0])
        uow.commit()
    assert post(api, body, manual=True, read=True).status_code == 201
    assert post(api, body, manual=True, read=True).status_code == 200


def test_new_routes_auth_disabled_and_permission(api, monkeypatch):
    from app.core.config import get_settings

    source = seed(api)
    body = body_for(api, source)
    client, key, *_ = api
    for headers, expected in [
        ({}, 401),
        (_headers(key, "user-a-subject", "communications:read"), 403),
    ]:
        assert (
            client.post(URL + "/from-analysis", json=body, headers=headers).status_code == expected
        )
        assert (
            client.get(
                URL + "/candidates",
                params={"source_kind": source[2], "source_id": str(source[1])},
                headers=headers,
            ).status_code
            == expected
        )
    monkeypatch.setenv("AUTH_MODE", "disabled")
    get_settings.cache_clear()
    assert client.post(URL + "/from-analysis", json=body).status_code == 401
    assert client.get(URL + "/candidates").status_code == 401


def test_confirmation_commit_failure_rolls_back(api, monkeypatch, log_events):
    from app.core.exceptions import PersistenceError
    from app.infrastructure.storage.unit_of_work import SqlAlchemyPersistenceUnitOfWork

    source = seed(api, kind="xlsx")
    body = body_for(api, source)

    def fail(_self):
        raise PersistenceError("PRIVATE SQL and credentials")

    monkeypatch.setattr(SqlAlchemyPersistenceUnitOfWork, "commit", fail)
    result = post(api, body, read=True)
    assert result.status_code == 503
    assert "PRIVATE" not in result.text and "PRIVATE" not in str(log_events)
    assert_counts(api, (0, 0, 0))


@pytest.mark.parametrize(
    "query",
    [
        {"limit": 0},
        {"limit": 101},
        {"offset": -1},
        {"extra": "unknown"},
        {"source_kind": "communication"},
    ],
)
def test_candidate_query_bounds(api, query):
    assert candidates(api, seed(api), **query).status_code == 422
    assert_counts(api, (0, 0, 0))


def test_candidate_requires_version_and_actual_source_field(api):
    source = seed(api, kind="xlsx")
    body = body_for(api, source)
    del body["candidate"]["projection_version"]
    assert post(api, body, read=True).status_code == 422
    body = body_for(api, source)
    body["candidate"]["field"] = "action_items"
    assert post(api, body, read=True).status_code == 422
    assert_counts(api, (0, 0, 0))


def test_manual_analysis_reference_and_candidate_validation(api):
    source = seed(api, kind="pdf")
    candidate = body_for(api, source)["candidate"]
    ref = dict(source_kind=source[2], source_id=str(source[1]), candidate=candidate)
    body = dict(creation_key="manual", kind="action", title="Reviewed", sources=[ref])
    assert post(api, body, read=True, manual=True).status_code == 201
    assert post(api, body, read=True, manual=True).status_code == 200
    tampered = ref | {"candidate": candidate | {"digest": "0" * 64}}
    assert (
        post(
            api, body | {"creation_key": "other", "sources": [tampered]}, read=True, manual=True
        ).json()["code"]
        == "work_item_candidate_changed"
    )
    wrong_id = ref | {"source_id": str(uuid4())}
    assert post(api, body | {"sources": [wrong_id]}, read=True, manual=True).status_code == 422
    assert_counts(api, (1, 1, 1))


def test_conversion_foreign_context_and_platform_owner_non_bypass(api):
    from app.infrastructure.storage.models import User
    from tests.unit.infrastructure.storage.test_business_work_item_repository import context

    origin = seed(api)
    foreign = seed(api, subject="foreign")
    with api[2]() as session:
        ctx = context(session, foreign[0])
        session.execute(update(User).where(User.id == origin[0]).values(application_role="owner"))
        session.commit()
    body = body_for(api, origin)
    response = post(api, body | {"business_context_id": str(ctx.id)})
    assert response.status_code == 404
    body["candidate"]["source_id"] = str(foreign[1])
    assert post(api, body).status_code == 404
    assert candidates(api, foreign).status_code == 404
    assert_counts(api, (0, 0, 0))


def test_candidate_hash_preserves_optional_fields_unicode_and_order():
    first = {"description": "  Résumé  ", "owner": None}
    second = {"owner": None, "description": "  Résumé  "}
    assert candidate_digest(first) == candidate_digest(second)
    assert candidate_digest(first) != candidate_digest({"description": "  Résumé  "})
    assert candidate_digest(first) != candidate_digest({"description": "Résumé", "owner": None})
