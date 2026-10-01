"""Phase 22C HTTP boundary, transaction and privacy tests using real local SQL."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api import dependencies as deps
from app.application.services.identity import IdentityResolver
from app.core.config import get_settings
from app.core.exceptions import PersistenceError
from app.core.security import AuthenticatedPrincipal
from app.infrastructure.storage.database import create_database_engine, create_session_factory
from app.infrastructure.storage.models import Base, User
from app.infrastructure.storage.unit_of_work import SqlAlchemyPersistenceUnitOfWork
from app.main import create_app
from tests.integration.test_business_contexts import (
    _analyze_headers,
    _clear_settings_env,
    _enable_oidc_env,
    _headers,
)
from tests.support.jwt_tokens import (
    TEST_ISSUER,
    TEST_PERMISSION,
    generate_test_rsa_private_key,
    make_test_validator,
)

URL = "/api/v1/work-items"


@pytest.fixture
def api(monkeypatch, log_events):
    _clear_settings_env(monkeypatch)
    _enable_oidc_env(monkeypatch)
    get_settings.cache_clear()
    engine = create_database_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)

    def uow_factory():
        return SqlAlchemyPersistenceUnitOfWork(factory)

    key = generate_test_rsa_private_key()
    validator = make_test_validator(key)
    app = create_app()
    app.dependency_overrides[deps.get_unit_of_work_factory] = lambda: uow_factory
    app.dependency_overrides[deps.get_token_validator] = lambda: validator

    def forbidden():
        raise AssertionError("tracking must not construct external side-effect dependencies")

    for dependency in (
        deps.get_ai_provider,
        deps.get_attachment_scanner,
        deps.get_communication_connector_factory,
        deps.get_communication_action_executor_factory,
    ):
        app.dependency_overrides[dependency] = forbidden
    with TestClient(app) as client:
        yield client, key, factory, uow_factory
    engine.dispose()


def create(api, **changes):
    client, key, *_ = api
    body = dict(creation_key="create-key", kind="action", title="Track this") | changes
    return client.post(URL, json=body, headers=_analyze_headers(key))


def test_create_retry_lost_response_and_privacy(api, log_events):
    client, key, factory, _ = api
    body = dict(title="  PRIVATE-TITLE  ", description=" PRIVATE-DESCRIPTION ", sources=[])
    first = create(api, **body)
    assert first.status_code == 201, first.text
    item = first.json()
    assert first.headers["location"] == f"{URL}/{item['id']}"
    assert item["version"] == 1 and item["status"] == "open"
    assert item["creation_origin"] == "manual" and item["confirmed_at"] is None
    assert item["due"] == {"kind": "none"} and item["business_context_id"] is None
    replay = create(api, title="PRIVATE-TITLE", description="PRIVATE-DESCRIPTION")
    assert replay.status_code == 200 and replay.json() == item
    assert replay.headers["location"] == first.headers["location"]
    changed = create(api, title="different")
    assert changed.status_code == 409
    assert changed.json()["code"] == "work_item_creation_key_conflict"
    detail = client.get(first.headers["location"], headers=_analyze_headers(key)).json()
    assert detail["sources"] == []
    events = client.get(first.headers["location"] + "/events", headers=_analyze_headers(key)).json()
    assert len(events["items"]) == 1
    assert "PRIVATE-" not in str(events)
    assert all(field not in str(events) for field in ("owner_user_id", "actor_user_id"))
    assert "PRIVATE-" not in str(log_events)
    with factory() as session:
        assert len(session.scalars(select(User)).all()) == 1


@pytest.mark.parametrize(
    "extra",
    [
        {"owner_user_id": str(uuid4())},
        {"actor": "x"},
        {"status": "completed"},
        {"version": 5},
        {"created_at": "2026-01-01"},
        {"creation_origin": "manual"},
        {"execution_target": "x"},
        {"sources": [{}]},
        {"sources": None},
        {"due": None},
        {"title": "  "},
        {"kind": "deadline"},
        {"creation_key": "invalid key"},
        {"due": {"kind": "none", "timezone": "UTC"}},
        {"due": {"kind": "date", "date": "2026-02-30", "timezone": "UTC"}},
        {"due": {"kind": "date", "date": "2026-01-01"}},
        {"due": {"kind": "date", "date": "2026-01-01", "timezone": "Invalid/Zone"}},
        {
            "due": {
                "kind": "datetime",
                "at": "2026-03-29T01:30:00+00:00",
                "timezone": "Europe/London",
            }
        },
        {"due": {"kind": "datetime", "at": "2026-01-01T01:30:00", "timezone": "UTC"}},
        {"due": {"kind": "datetime", "at": "2026-01-01T01:30:00+01:00", "timezone": "UTC"}},
    ],
)
def test_create_strict_inputs(api, extra):
    assert create(api, **extra).status_code == 422


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("post", "", {"creation_key": "k", "kind": "action", "title": "T"}),
        ("get", "", None),
        ("get", "/{id}", None),
        ("patch", "/{id}", {"expected_version": 1}),
        ("post", "/{id}/status", {"expected_version": 1, "status": "completed"}),
        ("post", "/{id}/archive", {"expected_version": 1}),
        ("post", "/{id}/restore", {"expected_version": 1}),
        ("get", "/{id}/events", None),
    ],
)
def test_authentication_capability_and_disabled(api, monkeypatch, method, path, body):
    client, key, *_ = api
    url = URL + path.replace("{id}", str(uuid4()))
    for headers, status in (
        ({}, 401),
        ({"Authorization": "Bearer broken"}, 401),
        (_headers(key, "user-a-subject", "communications:read"), 403),
    ):
        assert client.request(method, url, json=body, headers=headers).status_code == status
    monkeypatch.setenv("AUTH_MODE", "disabled")
    get_settings.cache_clear()
    assert client.request(method, url, json=body).status_code == 401


def test_owner_isolation_platform_owner_and_unmapped(api):
    client, key, factory, uow = api
    item = create(api).json()
    headers = _analyze_headers(key, "foreign-owner")
    assert client.get(URL, headers=headers).json()["items"] == []
    principal = AuthenticatedPrincipal(
        issuer=TEST_ISSUER, subject="foreign-owner", permissions=frozenset({TEST_PERMISSION})
    )
    owner = IdentityResolver(uow).resolve_or_create(principal)
    with factory() as session:
        session.get(User, owner).application_role = "owner"
        session.commit()
    for item_id in (item["id"], str(uuid4())):
        path = f"{URL}/{item_id}"
        for method, suffix, body in (
            ("get", "", None),
            ("get", "/events", None),
            ("patch", "", {"expected_version": 1, "title": "x"}),
            ("post", "/status", {"expected_version": 1, "status": "completed"}),
            ("post", "/archive", {"expected_version": 1}),
            ("post", "/restore", {"expected_version": 1}),
        ):
            r = client.request(method, path + suffix, json=body, headers=headers)
            assert r.status_code == 404 and r.json() == {
                "detail": "Work item or reference not found."
            }
    assert client.get(URL, headers=headers).json()["items"] == []


def test_lifecycle_versions_noops_reopen_archive(api):
    client, key, *_ = api
    item = create(api).json()
    path = f"{URL}/{item['id']}"
    headers = _analyze_headers(key)

    def mutate(suffix="", **body):
        return client.request(
            "post" if suffix else "patch", path + suffix, json=body, headers=headers
        )

    assert mutate(expected_version=1).json() == item
    assert mutate(expected_version=2).json()["code"] == "work_item_version_conflict"
    for status, version in [("in_progress", 1), ("open", 2), ("completed", 3)]:
        r = mutate("/status", expected_version=version, status=status)
        assert r.status_code == 200 and r.json()["version"] == version + 1
    assert mutate(expected_version=4, title="Edit").status_code == 409
    assert mutate("/status", expected_version=4, status="open").status_code == 409
    assert mutate("/status", expected_version=4, status="open", reopen=True).json()["version"] == 5
    archived = mutate("/archive", expected_version=5).json()
    assert archived["version"] == 6
    assert mutate("/archive", expected_version=6).json() == archived
    assert mutate("/status", expected_version=6, status="completed").status_code == 409
    assert mutate(expected_version=6).status_code == 409
    assert mutate("/restore", expected_version=6).json()["version"] == 7
    assert mutate("/restore", expected_version=7).json()["version"] == 7
    events = client.get(path + "/events", headers=headers).json()["items"]
    assert [e["item_version"] for e in events] == list(range(1, 8))
    assert all(e["event_ordinal"] == 0 for e in events)
    assert create(api).json()["version"] == 7  # replay returns current state


@pytest.mark.parametrize(
    "patch",
    [
        {"title": None},
        {"due": None},
        {"kind": "obligation"},
        {"sources": []},
        {"expected_version": True},
        {"expected_version": 0},
        {"expected_version": "1"},
    ],
)
def test_patch_strict(api, patch):
    client, key, *_ = api
    item = create(api).json()
    assert (
        client.patch(
            f"{URL}/{item['id']}",
            json={"expected_version": 1} | patch,
            headers=_analyze_headers(key),
        ).status_code
        == 422
    )


def test_context_move_detach_and_archived_context(api):
    client, key, *_ = api
    headers = _analyze_headers(key)

    def context():
        return client.post(
            "/api/v1/contexts", json={"type": "matter", "title": "C"}, headers=headers
        ).json()["id"]

    a, b = context(), context()
    item = create(api, business_context_id=a).json()
    path = f"{URL}/{item['id']}"
    r = client.patch(
        path,
        json={"expected_version": 1, "title": "new", "business_context_id": b},
        headers=headers,
    )
    assert r.status_code == 200 and r.json()["version"] == 2
    events = client.get(path + "/events", headers=headers).json()["items"]
    assert [e["event_type"] for e in events] == [
        "created",
        "edited",
        "context_disassociated",
        "context_associated",
    ]
    assert [e["context_at_event_id"] for e in events] == [a, a, a, b]
    assert [e["event_ordinal"] for e in events] == [0, 0, 1, 2]
    assert len({e["occurred_at"] for e in events[1:]}) == 1
    client.post(f"/api/v1/contexts/{b}/archive", headers=headers)
    assert client.get(path, headers=headers).json()["status"] == "open"
    assert (
        client.patch(
            path, json={"expected_version": 2, "business_context_id": None}, headers=headers
        ).status_code
        == 200
    )
    assert (
        client.patch(
            path, json={"expected_version": 3, "business_context_id": b}, headers=headers
        ).json()["code"]
        == "work_item_context_archived"
    )
    assert create(api, creation_key="other", business_context_id=b).status_code == 409
    assert create(api, creation_key="missing", business_context_id=str(uuid4())).status_code == 404
    foreign = _analyze_headers(key, "foreign")
    assert client.get(URL, params={"business_context_id": a}, headers=foreign).status_code == 404
    assert (
        client.get(URL, params={"business_context_id": str(uuid4())}, headers=headers).status_code
        == 404
    )


@pytest.mark.parametrize(
    "query",
    [
        {"limit": 0},
        {"limit": 101},
        {"offset": -1},
        {"unknown": "x"},
        {"business_context_id": str(uuid4()), "unassociated": "true"},
        {"due_date_from": "2026-01-01", "due_at_to": "2026-01-02T00:00:00Z"},
        {"due_date_from": "2026-02-01", "due_date_to": "2026-01-01"},
        {"due_kind": "datetime", "due_date_from": "2026-01-01"},
        {"due_kind": "none", "due_at_to": "2026-01-01T00:00:00Z"},
        {"due_at_from": "2026-01-01"},
        {"due_date_from": "2026-01-01T00:00:00Z"},
        {"sort": "due_asc"},
        {"sort": "due_asc", "due_date_from": "2026-01-01"},
        {"sort": "due_asc", "due_kind": "none"},
    ],
)
def test_query_validation(api, query):
    client, key, *_ = api
    assert client.get(URL, params=query, headers=_analyze_headers(key)).status_code == 422


def test_date_preservation_clear_and_pagination(api):
    client, key, *_ = api
    headers = _analyze_headers(key)
    due = {"kind": "date", "date": "2026-11-01", "timezone": "America/New_York"}
    item = create(api, due=due, description="desc").json()
    assert item["due"] == due
    path = f"{URL}/{item['id']}"
    assert client.get(path, headers=headers).json()["due"] == due
    assert (
        client.get(
            URL,
            params={"due_date_from": "2026-11-01", "due_date_to": "2026-11-01"},
            headers=headers,
        ).json()["items"][0]["id"]
        == item["id"]
    )
    create(api, creation_key="second")
    assert (
        client.get(URL, params={"limit": 1, "offset": 1}, headers=headers).json()["items"][0]["id"]
        == item["id"]
    )
    r = client.patch(
        path,
        json={"expected_version": 1, "description": None, "due": {"kind": "none"}},
        headers=headers,
    )
    assert r.json()["description"] is None and r.json()["due"] == {"kind": "none"}
    assert (
        client.get(path + "/events", params={"limit": 1, "offset": 1}, headers=headers).json()[
            "items"
        ][0]["event_type"]
        == "edited"
    )
    assert client.get(path + "/events", params={"limit": 101}, headers=headers).status_code == 422


def test_persistence_failure_atomicity_and_safe_logs(api, monkeypatch, log_events):
    client, key, factory, uow = api
    item = create(api).json()

    def failure(self):
        raise PersistenceError("SQL PRIVATE-TITLE SECRET")

    monkeypatch.setattr(SqlAlchemyPersistenceUnitOfWork, "commit", failure)
    headers = _analyze_headers(key)
    path = f"{URL}/{item['id']}"
    r = client.patch(path, json={"expected_version": 1, "title": "PRIVATE-TITLE"}, headers=headers)
    assert r.status_code == 503 and r.json()["detail"] == "Persistence is currently unavailable."
    assert client.get(path, headers=headers).json()["version"] == 1
    assert len(client.get(path + "/events", headers=headers).json()["items"]) == 1
    assert create(api, creation_key="fail").status_code == 503
    assert len(client.get(URL, headers=headers).json()["items"]) == 1
    assert "PRIVATE-TITLE" not in str(log_events) and "SECRET" not in str(log_events)


def test_tracking_routes_and_execution_separation(api):
    client, key, *_ = api
    paths = client.get("/openapi.json").json()["paths"]
    assert URL + "/candidates" in paths and URL + "/from-analysis" in paths
    assert "delete" not in paths[URL + "/{item_id}"]
    assert URL + "/{item_id}/sources" not in paths
    assert "/api/v1/workflow-actions" in paths


@pytest.mark.parametrize("case", ["title", "extra", "candidate", "query", "path"])
def test_tracking_validation_never_echoes_submitted_values(api, log_events, case):
    client, key, factory, _ = api
    sentinel = "PRIVATE-VALIDATION-CONTENT"
    headers = _analyze_headers(key)
    body = dict(creation_key="privacy", kind="action", title="Reviewed")
    if case == "title":
        body["title"] = sentinel * 20
        response = client.post(URL, json=body, headers=headers)
    elif case == "extra":
        body[sentinel] = {"token": sentinel}
        response = client.post(URL, json=body, headers=headers)
    elif case == "candidate":
        response = client.post(
            URL + "/from-analysis", json=body | {"candidate": {"digest": sentinel}},
            headers=headers,
        )
    elif case == "query":
        response = client.get(URL, params={"due_kind": sentinel}, headers=headers)
    else:
        response = client.get(URL + "/" + sentinel, headers=headers)
    assert response.status_code == 422
    assert sentinel not in response.text
    assert sentinel not in str(log_events)
    from app.schemas.errors import ErrorResponse

    payload = ErrorResponse.model_validate(response.json())
    if case == "title":
        assert "title" in payload.detail
    elif case == "candidate":
        assert "candidate" in payload.detail
    elif case == "query":
        assert "due_kind" in payload.detail
    elif case == "path":
        assert "item_id" in payload.detail
    from tests.unit.infrastructure.storage.test_business_work_item_repository import counts

    with factory() as session:
        assert counts(session) == (0, 0, 0)


@pytest.mark.parametrize("at", ["0001-01-01T00:00:00+14:00", "9999-12-31T23:59:59-12:00"])
@pytest.mark.parametrize("target", ["create", "filter"])
def test_out_of_range_due_instant_is_validation_error(api, at, target):
    client, key, *_ = api
    if target == "create":
        response = create(api, due={"kind": "datetime", "at": at, "timezone": "UTC"})
    else:
        response = client.get(URL, params={"due_at_from": at}, headers=_analyze_headers(key))
    assert response.status_code == 422
    assert at not in response.text


@pytest.mark.parametrize("value", ["\ud800", "\x00"])
@pytest.mark.parametrize("field", ["title", "description", "provider_message_id"])
def test_invalid_unicode_storage_text_fails_before_persistence(api, field, value):
    import json

    client, key, factory, _ = api
    body = dict(creation_key="encoding", kind="action", title="Reviewed")
    if field == "provider_message_id":
        body["sources"] = [{
            "source_kind": "communication", "connector_account_id": str(uuid4()),
            "provider_message_id": value,
        }]
    else:
        body[field] = value
    response = client.post(
        URL, content=json.dumps(body),
        headers=_analyze_headers(key) | {"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    from tests.unit.infrastructure.storage.test_business_work_item_repository import counts

    with factory() as session:
        assert counts(session) == (0, 0, 0)
