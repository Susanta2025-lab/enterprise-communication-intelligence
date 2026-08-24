"""Refreshable CommunicationCredentialResolver with lazy token acquisition.

``resolve()`` validates locator and provider only. Secret-store lookup, adapter
acquisition, cache, and compare-and-set rotation happen when the returned
callable is invoked. This preserves Phase 12 TX1: the factory may resolve
before commit, but token I/O stays after the unit of work closes.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

from app.core.exceptions import (
    CommunicationCredentialReauthorizationRequiredError,
    CommunicationCredentialUnavailableError,
    UnsupportedCommunicationCredentialProviderError,
)
from app.core.logging import get_logger
from app.core.telemetry import elapsed_ms, error_class
from app.domain.interfaces.communication_credential_resolver import (
    AccessTokenProvider,
    CommunicationCredentialResolver,
)
from app.domain.interfaces.communication_credential_store import (
    CommunicationCredentialRecord,
    CommunicationCredentialStore,
)
from app.infrastructure.credentials.refresh import (
    RefreshableCredentialAdapter,
    RefreshableCredentialResult,
)
from app.infrastructure.credentials.validation import (
    require_credential_ref,
    require_supported_provider,
)

logger = get_logger(__name__)

Clock = Callable[[], datetime]

_RESOLVER_BACKEND = "oauth_refreshable"
_REFRESH_SKEW = timedelta(minutes=5)
_CACHE_MAX_ENTRIES = 1024
_STORE_BACKEND_UNKNOWN = "unknown"


class OAuthCommunicationCredentialResolver(CommunicationCredentialResolver):
    """Resolve locators into on-demand refreshable access-token callables.

    This is not a Google or Microsoft OAuth implementation. Provider adapters
    are injected. The environment-backed resolver remains the local/dev
    runtime default until real mailbox credentials exist.
    """

    def __init__(
        self,
        store: CommunicationCredentialStore,
        adapters: Mapping[str, RefreshableCredentialAdapter],
        *,
        clock: Clock | None = None,
        refresh_skew: timedelta = _REFRESH_SKEW,
        cache_max_entries: int = _CACHE_MAX_ENTRIES,
        store_backend: str | None = None,
    ) -> None:
        self._store = store
        self._adapters = adapters
        self._clock = clock if clock is not None else _aware_utcnow
        self._skew = refresh_skew
        self._cache = _AccessTokenCache(cache_max_entries)
        self._locks = _KeyedLocks()
        backend = store_backend
        if backend is None:
            backend = getattr(store, "BACKEND_NAME", _STORE_BACKEND_UNKNOWN)
        self._store_backend = backend if isinstance(backend, str) else _STORE_BACKEND_UNKNOWN
        register = getattr(store, "add_mutation_listener", None)
        if callable(register):
            register(self._cache.invalidate)

    def __repr__(self) -> str:
        return "OAuthCommunicationCredentialResolver()"

    def resolve(
        self,
        *,
        credential_ref: str,
        provider: str,
    ) -> AccessTokenProvider:
        """Validate locator and provider, then return an on-demand token callable."""
        started_at = time.perf_counter()
        try:
            locator = require_credential_ref(credential_ref)
            provider_slug = require_supported_provider(provider)
            if provider_slug not in self._adapters:
                raise UnsupportedCommunicationCredentialProviderError()
        except (
            CommunicationCredentialUnavailableError,
            UnsupportedCommunicationCredentialProviderError,
        ) as exc:
            logger.warning(
                "communication_credential_resolution_failed",
                operation="resolve",
                resolver_backend=_RESOLVER_BACKEND,
                store_backend=self._store_backend,
                duration_ms=elapsed_ms(started_at),
                error_class=error_class(exc),
            )
            raise

        def provide_access_token() -> str:
            return self._provide_access_token(locator, provider_slug)

        return provide_access_token

    def _provide_access_token(self, locator: str, provider_slug: str) -> str:
        started_at = time.perf_counter()
        try:
            cached = self._cache.get_usable(provider_slug, locator, self._clock(), self._skew)
            if cached is not None:
                return cached
            with self._locks.acquire((provider_slug, locator)):
                cached = self._cache.get_usable(
                    provider_slug,
                    locator,
                    self._clock(),
                    self._skew,
                )
                if cached is not None:
                    return cached
                token = self._acquire_locked(locator, provider_slug)
            logger.info(
                "communication_credential_token_acquired",
                operation="provide_access_token",
                provider=provider_slug,
                resolver_backend=_RESOLVER_BACKEND,
                store_backend=self._store_backend,
                cache_status="miss",
                duration_ms=elapsed_ms(started_at),
            )
            return token
        except CommunicationCredentialReauthorizationRequiredError as exc:
            _log_token_failure(started_at, provider_slug, self._store_backend, exc)
            raise
        except CommunicationCredentialUnavailableError as exc:
            _log_token_failure(started_at, provider_slug, self._store_backend, exc)
            raise
        except UnsupportedCommunicationCredentialProviderError as exc:
            _log_token_failure(started_at, provider_slug, self._store_backend, exc)
            raise
        except Exception:
            unavailable = CommunicationCredentialUnavailableError()
            _log_token_failure(started_at, provider_slug, self._store_backend, unavailable)
            raise unavailable from None

    def _acquire_locked(self, locator: str, provider_slug: str) -> str:
        record = self._read_record(locator)
        token = self._acquire_from_record(locator, provider_slug, record)
        if token is not None:
            return token
        winner = self._read_record(locator)
        retried = self._acquire_from_record(locator, provider_slug, winner)
        if retried is not None:
            return retried
        raise CommunicationCredentialUnavailableError()

    def _acquire_from_record(
        self,
        locator: str,
        provider_slug: str,
        record: CommunicationCredentialRecord,
    ) -> str | None:
        if record.provider != provider_slug:
            raise CommunicationCredentialUnavailableError()
        adapter = self._adapters.get(provider_slug)
        if adapter is None:
            raise UnsupportedCommunicationCredentialProviderError()
        result = _call_adapter(adapter, provider_slug, record.secret_material)
        token, expires_at, replacement = self._require_usable_result(result)
        if replacement is None or replacement == record.secret_material:
            self._cache.put(provider_slug, locator, token, expires_at)
            return token
        replaced = self._replace_if_version(locator, record.version, replacement)
        if replaced is None:
            return None
        self._cache.put(provider_slug, locator, token, expires_at)
        return token

    def _read_record(self, locator: str) -> CommunicationCredentialRecord:
        try:
            record = self._store.get(locator)
        except CommunicationCredentialUnavailableError:
            raise
        except Exception:
            raise CommunicationCredentialUnavailableError() from None
        if record is None:
            raise CommunicationCredentialUnavailableError()
        return record

    def _replace_if_version(
        self,
        locator: str,
        expected_version: str,
        secret_material: bytes,
    ) -> CommunicationCredentialRecord | None:
        try:
            return self._store.replace_if_version(locator, expected_version, secret_material)
        except CommunicationCredentialUnavailableError:
            raise
        except Exception:
            raise CommunicationCredentialUnavailableError() from None

    def _require_usable_result(
        self,
        result: RefreshableCredentialResult,
    ) -> tuple[str, datetime, bytes | None]:
        token = result.access_token
        if not isinstance(token, str) or not token.strip():
            raise CommunicationCredentialUnavailableError()
        expires_at = result.expires_at
        if not isinstance(expires_at, datetime) or expires_at.tzinfo is None:
            raise CommunicationCredentialUnavailableError()
        if expires_at <= self._clock() + self._skew:
            raise CommunicationCredentialUnavailableError()
        replacement = result.replacement_secret_material
        if replacement is not None and (not isinstance(replacement, bytes) or not replacement):
            raise CommunicationCredentialUnavailableError()
        return token.strip(), expires_at, replacement


def build_oauth_communication_credential_resolver(
    store: CommunicationCredentialStore,
    adapters: Mapping[str, RefreshableCredentialAdapter],
    *,
    clock: Clock | None = None,
) -> OAuthCommunicationCredentialResolver:
    """Composition hook for 13C/13D. Not the production execute default."""
    return OAuthCommunicationCredentialResolver(store, adapters, clock=clock)


def _aware_utcnow() -> datetime:
    return datetime.now(UTC)


def _call_adapter(
    adapter: RefreshableCredentialAdapter,
    provider_slug: str,
    secret_material: bytes,
) -> RefreshableCredentialResult:
    try:
        result = adapter.acquire_access_token(
            provider=provider_slug,
            secret_material=secret_material,
        )
    except CommunicationCredentialReauthorizationRequiredError:
        raise
    except CommunicationCredentialUnavailableError:
        raise
    except UnsupportedCommunicationCredentialProviderError:
        raise
    except Exception:
        raise CommunicationCredentialUnavailableError() from None
    if not isinstance(result, RefreshableCredentialResult):
        raise CommunicationCredentialUnavailableError()
    return result


def _log_token_failure(
    started_at: float,
    provider_slug: str,
    store_backend: str,
    exc: Exception,
) -> None:
    logger.warning(
        "communication_credential_unavailable",
        operation="provide_access_token",
        provider=provider_slug,
        resolver_backend=_RESOLVER_BACKEND,
        store_backend=store_backend,
        duration_ms=elapsed_ms(started_at),
        error_class=error_class(exc),
    )


class _CachedToken:
    __slots__ = ("token", "expires_at")

    def __init__(self, token: str, expires_at: datetime) -> None:
        self.token = token
        self.expires_at = expires_at

    def __repr__(self) -> str:
        return "_CachedToken(expires_at=...)"


class _AccessTokenCache:
    def __init__(self, max_entries: int) -> None:
        self._max_entries = max_entries
        self._lock = threading.Lock()
        self._entries: OrderedDict[tuple[str, str], _CachedToken] = OrderedDict()

    def __repr__(self) -> str:
        return "_AccessTokenCache()"

    def get_usable(
        self,
        provider: str,
        locator: str,
        now: datetime,
        skew: timedelta,
    ) -> str | None:
        key = (provider, locator)
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry.expires_at <= now + skew:
                del self._entries[key]
                return None
            self._entries.move_to_end(key)
            return entry.token

    def put(
        self,
        provider: str,
        locator: str,
        token: str,
        expires_at: datetime,
    ) -> None:
        key = (provider, locator)
        with self._lock:
            self._entries[key] = _CachedToken(token, expires_at)
            self._entries.move_to_end(key)
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)

    def invalidate(self, locator: str) -> None:
        with self._lock:
            stale = [key for key in self._entries if key[1] == locator]
            for key in stale:
                del self._entries[key]


class _KeyedLocks:
    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._locks: dict[tuple[str, str], tuple[threading.Lock, int]] = {}

    @contextmanager
    def acquire(self, key: tuple[str, str]) -> Iterator[None]:
        with self._guard:
            lock, count = self._locks.get(key, (threading.Lock(), 0))
            self._locks[key] = (lock, count + 1)
        lock.acquire()
        try:
            yield
        finally:
            lock.release()
            with self._guard:
                current, count = self._locks[key]
                if count <= 1:
                    del self._locks[key]
                else:
                    self._locks[key] = (current, count - 1)
