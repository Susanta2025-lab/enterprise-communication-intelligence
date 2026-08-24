"""PostgreSQL advisory-lock coordination for cloud credential mutations."""

from __future__ import annotations

import threading

from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.domain.interfaces.communication_credential_store import NewCommunicationCredential
from app.infrastructure.credentials.azure_key_vault import (
    AzureKeyVaultCommunicationCredentialStore,
)
from app.infrastructure.credentials.locators import generate_credential_locator
from app.infrastructure.credentials.mutation import advisory_lock_keys
from app.infrastructure.storage.credential_mutation import (
    PostgresCredentialMutationCoordinator,
)
from tests.unit.infrastructure.credentials.cloud_fakes import FakeAzureSecretClient

_VAULT = "https://eci-dev.vault.azure.net"
_MATERIAL_A = b"concurrent-azure-secret-AAA"
_MATERIAL_B = b"concurrent-azure-secret-BBB"
_MATERIAL_C = b"concurrent-azure-create-CCC"
_MATERIAL_D = b"concurrent-azure-create-DDD"


def _coordinator(
    session_factory: sessionmaker[Session],
) -> PostgresCredentialMutationCoordinator:
    return PostgresCredentialMutationCoordinator(session_factory)


def _try_lock(session_factory: sessionmaker[Session], locator: str) -> bool:
    key1, key2 = advisory_lock_keys(locator)
    session = session_factory()
    try:
        acquired = session.execute(
            text("SELECT pg_try_advisory_xact_lock(:key1, :key2)"),
            {"key1": key1, "key2": key2},
        ).scalar()
        session.rollback()
        return bool(acquired)
    finally:
        session.close()


def _assert_secrets_absent_from_postgres(engine: Engine, *secrets: bytes) -> None:
    needles = [secret.decode("utf-8") for secret in secrets]
    with engine.connect() as connection:
        tables = (
            connection.execute(
                text("SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname = 'public'")
            )
            .scalars()
            .all()
        )
        blob_parts: list[str] = []
        for table in tables:
            rows = connection.execute(text(f'SELECT * FROM "{table}"')).mappings().all()
            blob_parts.append(str(rows))
        blob = "".join(blob_parts)
    for needle in needles:
        assert needle not in blob


def test_same_locator_advisory_lock_serializes(
    session_factory: sessionmaker[Session],
) -> None:
    locator = generate_credential_locator()
    first = _coordinator(session_factory)
    second = _coordinator(session_factory)
    acquired = threading.Event()
    release = threading.Event()
    trying = threading.Event()
    entered = threading.Event()
    errors: list[BaseException] = []

    def holder() -> None:
        try:
            with first.lock(locator):
                acquired.set()
                assert release.wait(timeout=5)
        except BaseException as exc:
            errors.append(exc)

    def waiter() -> None:
        try:
            assert acquired.wait(timeout=5)
            trying.set()
            with second.lock(locator):
                entered.set()
        except BaseException as exc:
            errors.append(exc)

    holder_thread = threading.Thread(target=holder)
    waiter_thread = threading.Thread(target=waiter)
    holder_thread.start()
    assert acquired.wait(timeout=5)
    assert _try_lock(session_factory, locator) is False
    waiter_thread.start()
    assert trying.wait(timeout=5)
    waiter_thread.join(timeout=0.4)
    assert waiter_thread.is_alive()
    assert not entered.is_set()
    release.set()
    holder_thread.join(timeout=5)
    waiter_thread.join(timeout=5)
    assert entered.is_set()
    assert errors == []


def test_independent_locators_do_not_share_a_lock(
    session_factory: sessionmaker[Session],
) -> None:
    left = generate_credential_locator()
    right = generate_credential_locator()
    first = _coordinator(session_factory)
    second = _coordinator(session_factory)
    barrier = threading.Barrier(2)
    entered: list[str] = []
    errors: list[BaseException] = []

    def worker(
        coordinator: PostgresCredentialMutationCoordinator,
        locator: str,
    ) -> None:
        try:
            with coordinator.lock(locator):
                entered.append(locator)
                barrier.wait(timeout=5)
        except BaseException as exc:
            errors.append(exc)

    threads = [
        threading.Thread(target=worker, args=(first, left)),
        threading.Thread(target=worker, args=(second, right)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
        assert not thread.is_alive()
    assert errors == []
    assert set(entered) == {left, right}


def test_concurrent_azure_replace_if_version_one_winner(
    postgres_engine: Engine,
    session_factory: sessionmaker[Session],
) -> None:
    fake = FakeAzureSecretClient()
    locator = generate_credential_locator()
    setup = AzureKeyVaultCommunicationCredentialStore(
        _VAULT,
        secret_client=fake,
        mutation_coordinator=_coordinator(session_factory),
    )
    created = setup.create(NewCommunicationCredential(locator, "gmail", _MATERIAL_A))
    store_a = AzureKeyVaultCommunicationCredentialStore(
        _VAULT,
        secret_client=fake,
        mutation_coordinator=_coordinator(session_factory),
    )
    store_b = AzureKeyVaultCommunicationCredentialStore(
        _VAULT,
        secret_client=fake,
        mutation_coordinator=_coordinator(session_factory),
    )
    start = threading.Barrier(2)
    results: list[object] = [None, None]
    errors: list[BaseException] = []

    def worker(
        index: int, store: AzureKeyVaultCommunicationCredentialStore, material: bytes
    ) -> None:
        try:
            start.wait(timeout=5)
            results[index] = store.replace_if_version(locator, created.version, material)
        except BaseException as exc:
            errors.append(exc)

    threads = [
        threading.Thread(target=worker, args=(0, store_a, _MATERIAL_B)),
        threading.Thread(target=worker, args=(1, store_b, _MATERIAL_C)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive()
    assert errors == []
    winners = [item for item in results if item is not None]
    losers = [item for item in results if item is None]
    assert len(winners) == 1
    assert len(losers) == 1
    current = store_a.get(locator)
    assert current is not None
    assert current.secret_material in {_MATERIAL_B, _MATERIAL_C}
    assert current.secret_material == winners[0].secret_material  # type: ignore[union-attr]
    _assert_secrets_absent_from_postgres(
        postgres_engine,
        _MATERIAL_A,
        _MATERIAL_B,
        _MATERIAL_C,
    )


def test_concurrent_azure_create_one_winner(
    postgres_engine: Engine,
    session_factory: sessionmaker[Session],
) -> None:
    from app.core.exceptions import CommunicationCredentialConflictError

    fake = FakeAzureSecretClient()
    locator = generate_credential_locator()
    store_a = AzureKeyVaultCommunicationCredentialStore(
        _VAULT,
        secret_client=fake,
        mutation_coordinator=_coordinator(session_factory),
    )
    store_b = AzureKeyVaultCommunicationCredentialStore(
        _VAULT,
        secret_client=fake,
        mutation_coordinator=_coordinator(session_factory),
    )
    start = threading.Barrier(2)
    outcomes: list[str] = []
    errors: list[BaseException] = []

    def worker(store: AzureKeyVaultCommunicationCredentialStore, material: bytes) -> None:
        try:
            start.wait(timeout=5)
            store.create(NewCommunicationCredential(locator, "gmail", material))
            outcomes.append("created")
        except CommunicationCredentialConflictError:
            outcomes.append("conflict")
        except BaseException as exc:
            errors.append(exc)

    threads = [
        threading.Thread(target=worker, args=(store_a, _MATERIAL_C)),
        threading.Thread(target=worker, args=(store_b, _MATERIAL_D)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive()
    assert errors == []
    assert outcomes.count("created") == 1
    assert outcomes.count("conflict") == 1
    current = store_a.get(locator)
    assert current is not None
    assert current.secret_material in {_MATERIAL_C, _MATERIAL_D}
    _assert_secrets_absent_from_postgres(postgres_engine, _MATERIAL_C, _MATERIAL_D)
