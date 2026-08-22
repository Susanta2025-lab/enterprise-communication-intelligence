"""Shared helpers for refreshable credential resolver tests."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from app.domain.interfaces.communication_credential_store import (
    CommunicationCredentialRecord,
    CommunicationCredentialStore,
    NewCommunicationCredential,
)
from app.infrastructure.credentials.memory import InMemoryCommunicationCredentialStore
from app.infrastructure.credentials.oauth import OAuthCommunicationCredentialResolver
from app.infrastructure.credentials.refresh import RefreshableCredentialResult

FUTURE = datetime(2030, 1, 1, tzinfo=UTC)
NOW = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)


class MutableClock:
    def __init__(self, now: datetime = NOW) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


class FakeRefreshAdapter:
    def __init__(
        self,
        *,
        token: str = "access-token",
        expires_at: datetime = FUTURE,
        replacement: bytes | None = None,
        factory: Callable[[str, bytes], RefreshableCredentialResult] | None = None,
    ) -> None:
        self.calls: list[tuple[str, bytes]] = []
        self.token = token
        self.expires_at = expires_at
        self.replacement = replacement
        self.factory = factory
        self.error: Exception | None = None

    def acquire_access_token(
        self,
        *,
        provider: str,
        secret_material: bytes,
    ) -> RefreshableCredentialResult:
        self.calls.append((provider, secret_material))
        if self.error is not None:
            raise self.error
        if self.factory is not None:
            return self.factory(provider, secret_material)
        return RefreshableCredentialResult(self.token, self.expires_at, self.replacement)


class CountingStore:
    def __init__(self, inner: CommunicationCredentialStore | None = None) -> None:
        self.inner = inner or InMemoryCommunicationCredentialStore()
        self.gets = 0
        self.creates = 0
        self.replaces = 0
        self.deletes = 0
        self.BACKEND_NAME = getattr(self.inner, "BACKEND_NAME", "memory")

    def add_mutation_listener(self, listener: Callable[[str], None]) -> None:
        register = getattr(self.inner, "add_mutation_listener", None)
        if callable(register):
            register(listener)

    def create(
        self,
        credential: NewCommunicationCredential,
    ) -> CommunicationCredentialRecord:
        self.creates += 1
        return self.inner.create(credential)

    def get(self, credential_ref: str) -> CommunicationCredentialRecord | None:
        self.gets += 1
        return self.inner.get(credential_ref)

    def replace_if_version(
        self,
        credential_ref: str,
        expected_version: str,
        secret_material: bytes,
    ) -> CommunicationCredentialRecord | None:
        self.replaces += 1
        return self.inner.replace_if_version(
            credential_ref,
            expected_version,
            secret_material,
        )

    def delete(self, credential_ref: str) -> None:
        self.deletes += 1
        self.inner.delete(credential_ref)


def seed_credential(
    store: CommunicationCredentialStore,
    *,
    locator: str = "oauth-testlocator0001",
    provider: str = "gmail",
    secret_material: bytes = b"opaque-secret-v1",
) -> CommunicationCredentialRecord:
    return store.create(NewCommunicationCredential(locator, provider, secret_material))


def build_resolver(
    store: CommunicationCredentialStore,
    adapters: dict[str, FakeRefreshAdapter],
    *,
    clock: MutableClock | None = None,
) -> OAuthCommunicationCredentialResolver:
    return OAuthCommunicationCredentialResolver(
        store,
        adapters,
        clock=clock or MutableClock(),
    )


def usable_expiry(clock: MutableClock, minutes: int = 60) -> datetime:
    return clock.now + timedelta(minutes=minutes)
