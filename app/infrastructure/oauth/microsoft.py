"""Microsoft identity platform v2 and Graph refresh adapters.

Microsoft HTTP and JWT verification stay inside this module. Application and
domain layers receive provider-neutral URLs, capabilities, and opaque secret
bytes only. The Microsoft Authentication Library is not used.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, quote, urlencode, urlparse

import httpx
import jwt
from jwt import PyJWKClient
from jwt.exceptions import PyJWTError

from app.core.exceptions import (
    CommunicationCredentialReauthorizationRequiredError,
    CommunicationCredentialUnavailableError,
    MailboxOAuthAuthorizationFailedError,
    ServiceUnavailableError,
    UnsupportedCommunicationCredentialProviderError,
)
from app.core.logging import get_logger
from app.core.telemetry import elapsed_ms, error_class
from app.domain.enums import CommunicationCapability
from app.domain.interfaces.mailbox_oauth_client import (
    MailboxOAuthAuthorizationResult,
    MailboxOAuthClient,
)
from app.domain.models.capabilities import normalize_communication_capabilities
from app.infrastructure.credentials.refresh import RefreshableCredentialResult

logger = get_logger(__name__)

MICROSOFT_LOGIN_HOST = "login.microsoftonline.com"
MICROSOFT_AUTHORIZE_PATH = "/oauth2/v2.0/authorize"
MICROSOFT_TOKEN_PATH = "/oauth2/v2.0/token"
OPENID_SCOPE = "openid"
PROFILE_SCOPE = "profile"
OFFLINE_ACCESS_SCOPE = "offline_access"
GRAPH_MAIL_READ_SCOPE = "https://graph.microsoft.com/Mail.Read"
GRAPH_MAIL_SEND_SCOPE = "https://graph.microsoft.com/Mail.Send"
REQUESTED_MICROSOFT_OAUTH_SCOPES: tuple[str, ...] = (
    OPENID_SCOPE,
    PROFILE_SCOPE,
    OFFLINE_ACCESS_SCOPE,
    GRAPH_MAIL_READ_SCOPE,
    GRAPH_MAIL_SEND_SCOPE,
)
# Personal Microsoft accounts use this well-known directory tenant.
MSA_TENANT_ID = "9188040d-6c67-4c5b-b112-36a304b66dad"
_GUID_PATTERN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_SAFE_OAUTH_ERROR = re.compile(r"^[a-z0-9_]{1,64}$")
_GRAPH_SCOPE_PREFIX = "https://graph.microsoft.com/"
_SCOPE_TO_CAPABILITY = {
    "mail.read": CommunicationCapability.MAIL_READ,
    "mail.send": CommunicationCapability.MAIL_SEND,
}
_MATERIAL_VERSION = 1
_PROVIDER = "microsoft_graph"
_UNAVAILABLE = "Microsoft mailbox authorization is unavailable."
_CODE_CHALLENGE_METHOD = "S256"
_TOKEN_TIMEOUT = httpx.Timeout(15.0)
_ALLOWED_JWT_ALGORITHMS = ("RS256",)

TokenFetcher = Callable[[str, str], Mapping[str, Any]]
IdTokenVerifier = Callable[[str], Mapping[str, Any]]
RefreshTransport = Callable[[Mapping[str, str]], Mapping[str, Any]]


@dataclass(frozen=True, slots=True)
class _MicrosoftMailboxSecret:
    """Refreshable Microsoft mailbox material. Access and ID tokens are omitted.

    Durable mailbox identity is ``{tid}:{oid}`` from the verified v2 ID token.
    ``tid`` is the Entra/MSA directory tenant. ``oid`` is the immutable object
    identifier in that tenant. Email, UPN, and pairwise ``sub`` are not used.
    """

    refresh_token: str = field(repr=False)
    scopes: tuple[str, ...]
    tenant_id: str
    object_id: str

    @property
    def external_account_id(self) -> str:
        return f"{self.tenant_id}:{self.object_id}"

    def __repr__(self) -> str:
        return "_MicrosoftMailboxSecret(schema_version=1)"


class MicrosoftMailboxOAuthClient(MailboxOAuthClient):
    """Confidential web-server Microsoft authorization-code client."""

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        tenant: str,
        token_fetcher: TokenFetcher | None = None,
        id_token_verifier: IdTokenVerifier | None = None,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._tenant = tenant
        self._token_fetcher = token_fetcher
        self._id_token_verifier = id_token_verifier

    def __repr__(self) -> str:
        return "MicrosoftMailboxOAuthClient()"

    def build_authorization_url(
        self,
        *,
        state: str,
        code_challenge: str,
        code_challenge_method: str,
    ) -> str:
        """Build a Microsoft v2 authorization URL using Phase 13A state and PKCE."""
        started_at = time.perf_counter()
        if not state or not code_challenge or code_challenge_method != _CODE_CHALLENGE_METHOD:
            raise MailboxOAuthAuthorizationFailedError()
        try:
            url = _authorization_url(
                tenant=self._tenant,
                client_id=self._client_id,
                redirect_uri=self._redirect_uri,
                state=state,
                code_challenge=code_challenge,
            )
        except MailboxOAuthAuthorizationFailedError:
            raise
        except Exception as exc:
            logger.warning(
                "microsoft_oauth_authorization_url_failed",
                operation="build_authorization_url",
                duration_ms=elapsed_ms(started_at),
                error_class=error_class(exc),
            )
            raise MailboxOAuthAuthorizationFailedError() from None
        if not _url_matches_session(
            url,
            tenant=self._tenant,
            state=state,
            code_challenge=code_challenge,
            redirect_uri=self._redirect_uri,
            client_id=self._client_id,
        ):
            logger.warning(
                "microsoft_oauth_authorization_url_rejected",
                operation="build_authorization_url",
                duration_ms=elapsed_ms(started_at),
                error_class="AuthorizationUrlMismatch",
            )
            raise MailboxOAuthAuthorizationFailedError()
        logger.info(
            "microsoft_oauth_authorization_url_built",
            operation="build_authorization_url",
            duration_ms=elapsed_ms(started_at),
        )
        return url

    def exchange_authorization_code(
        self,
        *,
        code: str,
        code_verifier: str,
    ) -> MailboxOAuthAuthorizationResult:
        """Exchange the one-time code. Does not persist tokens."""
        started_at = time.perf_counter()
        if not isinstance(code, str) or not code or not isinstance(code_verifier, str):
            raise MailboxOAuthAuthorizationFailedError()
        if not code_verifier:
            raise MailboxOAuthAuthorizationFailedError()
        try:
            token_response = self._fetch_token_response(code, code_verifier)
            refresh_token = token_response.get("refresh_token")
            id_token_jwt = token_response.get("id_token")
            if not isinstance(refresh_token, str) or not refresh_token:
                raise MailboxOAuthAuthorizationFailedError()
            if not isinstance(id_token_jwt, str) or not id_token_jwt:
                raise MailboxOAuthAuthorizationFailedError()
            claims = self._verify_id_token(id_token_jwt)
            _require_issuer_matches_tenant(claims, self._tenant)
            tenant_id, object_id = _durable_microsoft_identity(claims)
            granted_scopes = _parse_granted_scopes(token_response)
            capabilities = _capabilities_from_scopes(granted_scopes)
            material = serialize_microsoft_mailbox_secret(
                refresh_token=refresh_token,
                scopes=granted_scopes,
                tenant_id=tenant_id,
                object_id=object_id,
            )
        except MailboxOAuthAuthorizationFailedError:
            logger.warning(
                "microsoft_oauth_code_exchange_failed",
                operation="exchange_authorization_code",
                duration_ms=elapsed_ms(started_at),
                error_class="MailboxOAuthAuthorizationFailedError",
            )
            raise
        except ServiceUnavailableError:
            logger.warning(
                "microsoft_oauth_code_exchange_unavailable",
                operation="exchange_authorization_code",
                duration_ms=elapsed_ms(started_at),
                error_class="ServiceUnavailableError",
            )
            raise
        except Exception as exc:
            if _is_transport_failure(exc):
                logger.warning(
                    "microsoft_oauth_code_exchange_unavailable",
                    operation="exchange_authorization_code",
                    duration_ms=elapsed_ms(started_at),
                    error_class=error_class(exc),
                )
                raise ServiceUnavailableError(_UNAVAILABLE) from None
            logger.warning(
                "microsoft_oauth_code_exchange_failed",
                operation="exchange_authorization_code",
                duration_ms=elapsed_ms(started_at),
                error_class=error_class(exc),
            )
            raise MailboxOAuthAuthorizationFailedError() from None
        logger.info(
            "microsoft_oauth_code_exchanged",
            operation="exchange_authorization_code",
            duration_ms=elapsed_ms(started_at),
        )
        return MailboxOAuthAuthorizationResult(
            external_account_id=f"{tenant_id}:{object_id}",
            granted_capabilities=capabilities,
            secret_material=material,
        )

    def _fetch_token_response(self, code: str, code_verifier: str) -> Mapping[str, Any]:
        if self._token_fetcher is not None:
            try:
                fetched = self._token_fetcher(code, code_verifier)
            except MailboxOAuthAuthorizationFailedError:
                raise
            except ServiceUnavailableError:
                raise
            except Exception as exc:
                if _is_transport_failure(exc):
                    raise ServiceUnavailableError(_UNAVAILABLE) from None
                raise MailboxOAuthAuthorizationFailedError() from None
            if not isinstance(fetched, Mapping):
                raise MailboxOAuthAuthorizationFailedError()
            return fetched
        form = {
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self._redirect_uri,
            "code_verifier": code_verifier,
        }
        return _post_token_form(
            tenant=self._tenant,
            form=form,
            operation="exchange_authorization_code",
            on_invalid_grant=MailboxOAuthAuthorizationFailedError,
            on_client_error=MailboxOAuthAuthorizationFailedError,
        )

    def _verify_id_token(self, token: str) -> Mapping[str, Any]:
        if self._id_token_verifier is not None:
            try:
                claims = self._id_token_verifier(token)
            except MailboxOAuthAuthorizationFailedError:
                raise
            except ServiceUnavailableError:
                raise
            except Exception as exc:
                if _is_transport_failure(exc):
                    raise ServiceUnavailableError(_UNAVAILABLE) from None
                raise MailboxOAuthAuthorizationFailedError() from None
            if not isinstance(claims, Mapping):
                raise MailboxOAuthAuthorizationFailedError()
            return claims
        try:
            claims = verify_microsoft_id_token(
                token,
                client_id=self._client_id,
                tenant=self._tenant,
            )
        except MailboxOAuthAuthorizationFailedError:
            raise
        except ServiceUnavailableError:
            raise
        except Exception as exc:
            if _is_transport_failure(exc):
                raise ServiceUnavailableError(_UNAVAILABLE) from None
            raise MailboxOAuthAuthorizationFailedError() from None
        if not isinstance(claims, Mapping):
            raise MailboxOAuthAuthorizationFailedError()
        return claims


class MicrosoftRefreshableCredentialAdapter:
    """Refresh Graph access tokens from stored Microsoft secret material."""

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        tenant: str,
        refresh_transport: RefreshTransport | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._tenant = tenant
        self._refresh_transport = refresh_transport
        self._clock = clock if clock is not None else (lambda: datetime.now(UTC))

    def __repr__(self) -> str:
        return "MicrosoftRefreshableCredentialAdapter()"

    def acquire_access_token(
        self,
        *,
        provider: str,
        secret_material: bytes,
    ) -> RefreshableCredentialResult:
        if provider != _PROVIDER:
            raise UnsupportedCommunicationCredentialProviderError()
        started_at = time.perf_counter()
        try:
            stored = deserialize_microsoft_mailbox_secret(secret_material)
            payload = self._refresh(stored)
            access_token = payload.get("access_token")
            if not isinstance(access_token, str) or not access_token.strip():
                raise CommunicationCredentialUnavailableError()
            expires_at = _expiry_from_token_response(payload, self._clock())
            replacement = _replacement_secret_material(stored, payload)
            logger.info(
                "microsoft_oauth_access_token_refreshed",
                operation="acquire_access_token",
                duration_ms=elapsed_ms(started_at),
            )
            return RefreshableCredentialResult(
                access_token=access_token.strip(),
                expires_at=expires_at,
                replacement_secret_material=replacement,
            )
        except CommunicationCredentialReauthorizationRequiredError:
            logger.warning(
                "microsoft_oauth_refresh_reauthorization_required",
                operation="acquire_access_token",
                duration_ms=elapsed_ms(started_at),
                error_class="CommunicationCredentialReauthorizationRequiredError",
            )
            raise
        except CommunicationCredentialUnavailableError:
            logger.warning(
                "microsoft_oauth_refresh_unavailable",
                operation="acquire_access_token",
                duration_ms=elapsed_ms(started_at),
                error_class="CommunicationCredentialUnavailableError",
            )
            raise
        except UnsupportedCommunicationCredentialProviderError:
            raise
        except Exception as exc:
            mapped = _map_refresh_exception(exc)
            logger.warning(
                "microsoft_oauth_refresh_unavailable",
                operation="acquire_access_token",
                duration_ms=elapsed_ms(started_at),
                error_class=error_class(mapped),
            )
            raise mapped from None

    def _refresh(self, stored: _MicrosoftMailboxSecret) -> Mapping[str, Any]:
        form = {
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "grant_type": "refresh_token",
            "refresh_token": stored.refresh_token,
        }
        if self._refresh_transport is not None:
            try:
                fetched = self._refresh_transport(form)
            except (
                CommunicationCredentialReauthorizationRequiredError,
                CommunicationCredentialUnavailableError,
            ):
                raise
            except Exception as exc:
                raise _map_refresh_exception(exc) from None
            if not isinstance(fetched, Mapping):
                raise CommunicationCredentialUnavailableError()
            return fetched
        return _post_token_form(
            tenant=self._tenant,
            form=form,
            operation="acquire_access_token",
            on_invalid_grant=CommunicationCredentialReauthorizationRequiredError,
            on_client_error=CommunicationCredentialUnavailableError,
        )


def serialize_microsoft_mailbox_secret(
    *,
    refresh_token: str,
    scopes: tuple[str, ...],
    tenant_id: str,
    object_id: str,
) -> bytes:
    """Serialize Microsoft-private refresh material. Omits access and ID tokens."""
    payload = {
        "v": _MATERIAL_VERSION,
        "rt": refresh_token,
        "sc": list(scopes),
        "tid": tenant_id,
        "oid": object_id,
    }
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")


def deserialize_microsoft_mailbox_secret(secret_material: bytes) -> _MicrosoftMailboxSecret:
    """Parse stored Microsoft refresh material or raise unavailability."""
    if not isinstance(secret_material, bytes) or not secret_material:
        raise CommunicationCredentialUnavailableError()
    try:
        payload = json.loads(secret_material.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise CommunicationCredentialUnavailableError() from None
    if not isinstance(payload, dict) or payload.get("v") != _MATERIAL_VERSION:
        raise CommunicationCredentialUnavailableError()
    refresh_token = payload.get("rt")
    tenant_id = payload.get("tid")
    object_id = payload.get("oid")
    scopes_value = payload.get("sc")
    if not isinstance(refresh_token, str) or not refresh_token:
        raise CommunicationCredentialUnavailableError()
    if not isinstance(tenant_id, str) or not _is_guid(tenant_id):
        raise CommunicationCredentialUnavailableError()
    if not isinstance(object_id, str) or not _is_guid(object_id):
        raise CommunicationCredentialUnavailableError()
    if not isinstance(scopes_value, list) or not all(
        isinstance(item, str) and item for item in scopes_value
    ):
        raise CommunicationCredentialUnavailableError()
    return _MicrosoftMailboxSecret(
        refresh_token=refresh_token,
        scopes=tuple(scopes_value),
        tenant_id=tenant_id.lower(),
        object_id=object_id.lower(),
    )


def verify_microsoft_id_token(
    token: str,
    *,
    client_id: str,
    tenant: str,
) -> Mapping[str, Any]:
    """Verify a Microsoft v2 ID token signature, audience, issuer, and tenant."""
    if not isinstance(token, str) or not token:
        raise MailboxOAuthAuthorizationFailedError()
    jwks_url = f"https://{MICROSOFT_LOGIN_HOST}/{tenant}/discovery/v2.0/keys"
    try:
        jwks_client = PyJWKClient(jwks_url, cache_jwk_set=True, lifespan=300)
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=list(_ALLOWED_JWT_ALGORITHMS),
            audience=client_id,
            options={
                "require": ["exp", "iss", "aud", "oid", "tid"],
                "verify_iss": False,
            },
        )
    except MailboxOAuthAuthorizationFailedError:
        raise
    except Exception as exc:
        if _is_transport_failure(exc):
            raise ServiceUnavailableError(_UNAVAILABLE) from None
        if isinstance(exc, PyJWTError):
            raise MailboxOAuthAuthorizationFailedError() from None
        raise MailboxOAuthAuthorizationFailedError() from None
    if not isinstance(claims, Mapping):
        raise MailboxOAuthAuthorizationFailedError()
    _require_issuer_matches_tenant(claims, tenant)
    return claims


def microsoft_authority_base(tenant: str) -> str:
    """Return the Microsoft identity platform v2 authority for a validated tenant."""
    return f"https://{MICROSOFT_LOGIN_HOST}/{tenant}"


def _authorization_url(
    *,
    tenant: str,
    client_id: str,
    redirect_uri: str,
    state: str,
    code_challenge: str,
) -> str:
    query = urlencode(
        {
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "response_mode": "query",
            "scope": " ".join(REQUESTED_MICROSOFT_OAUTH_SCOPES),
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": _CODE_CHALLENGE_METHOD,
            "prompt": "consent",
        },
        quote_via=quote,
    )
    return f"{microsoft_authority_base(tenant)}{MICROSOFT_AUTHORIZE_PATH}?{query}"


def _url_matches_session(
    url: str,
    *,
    tenant: str,
    state: str,
    code_challenge: str,
    redirect_uri: str,
    client_id: str,
) -> bool:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != MICROSOFT_LOGIN_HOST:
        return False
    expected_path = f"/{tenant}{MICROSOFT_AUTHORIZE_PATH}"
    if parsed.path != expected_path:
        return False
    params = parse_qs(parsed.query, keep_blank_values=True)
    if params.get("state") != [state]:
        return False
    if params.get("code_challenge") != [code_challenge]:
        return False
    if params.get("code_challenge_method") != [_CODE_CHALLENGE_METHOD]:
        return False
    if params.get("redirect_uri") != [redirect_uri]:
        return False
    if params.get("client_id") != [client_id]:
        return False
    if params.get("response_type") != ["code"]:
        return False
    if params.get("prompt") != ["consent"]:
        return False
    if params.get("response_mode") != ["query"]:
        return False
    scopes = _split_scope_value(params.get("scope", [""])[0])
    if tuple(scopes) != REQUESTED_MICROSOFT_OAUTH_SCOPES:
        return False
    return True


def _post_token_form(
    *,
    tenant: str,
    form: Mapping[str, str],
    operation: str,
    on_invalid_grant: type[Exception],
    on_client_error: type[Exception],
) -> Mapping[str, Any]:
    token_url = f"{microsoft_authority_base(tenant)}{MICROSOFT_TOKEN_PATH}"
    try:
        with httpx.Client(timeout=_TOKEN_TIMEOUT, follow_redirects=False) as client:
            response = client.post(token_url, data=dict(form))
    except Exception as exc:
        if _is_transport_failure(exc):
            raise ServiceUnavailableError(_UNAVAILABLE) from None
        raise on_client_error() from None
    status = response.status_code
    payload = _json_object_or_none(response)
    oauth_error = _safe_oauth_error(payload)
    if status >= 500 or status == 429:
        logger.warning(
            "microsoft_oauth_token_http_error",
            operation=operation,
            http_status=status,
            oauth_error=oauth_error,
        )
        raise ServiceUnavailableError(_UNAVAILABLE)
    if status in {400, 401}:
        logger.warning(
            "microsoft_oauth_token_http_error",
            operation=operation,
            http_status=status,
            oauth_error=oauth_error,
        )
        if oauth_error == "invalid_grant":
            raise on_invalid_grant()
        raise on_client_error()
    if status != 200 or payload is None:
        logger.warning(
            "microsoft_oauth_token_http_error",
            operation=operation,
            http_status=status,
            oauth_error=oauth_error,
        )
        raise on_client_error()
    return payload


def _json_object_or_none(response: httpx.Response) -> dict[str, Any] | None:
    try:
        payload = response.json()
    except Exception:
        return None
    if isinstance(payload, dict):
        return payload
    return None


def _safe_oauth_error(payload: Mapping[str, Any] | None) -> str | None:
    if payload is None:
        return None
    raw = payload.get("error")
    if not isinstance(raw, str):
        return None
    candidate = raw.strip().lower()
    if not _SAFE_OAUTH_ERROR.fullmatch(candidate):
        return None
    return candidate


def _durable_microsoft_identity(claims: Mapping[str, Any]) -> tuple[str, str]:
    """Return lowercase ``(tid, oid)`` from a verified ID token.

    Microsoft ``sub`` is pairwise per application and is not the mailbox identity.
    Email, UPN, and preferred_username are not durable identifiers.
    """
    tenant_id = claims.get("tid")
    object_id = claims.get("oid")
    if not isinstance(tenant_id, str) or not _is_guid(tenant_id):
        raise MailboxOAuthAuthorizationFailedError()
    if not isinstance(object_id, str) or not _is_guid(object_id):
        raise MailboxOAuthAuthorizationFailedError()
    return tenant_id.lower(), object_id.lower()


def _require_issuer_matches_tenant(claims: Mapping[str, Any], configured_tenant: str) -> None:
    tenant_id, _object_id = _durable_microsoft_identity(claims)
    issuer = claims.get("iss")
    expected = f"https://{MICROSOFT_LOGIN_HOST}/{tenant_id}/v2.0"
    if not isinstance(issuer, str) or issuer.rstrip("/") != expected:
        raise MailboxOAuthAuthorizationFailedError()
    configured = configured_tenant.lower()
    if configured == "common":
        return
    if configured == "consumers":
        if tenant_id != MSA_TENANT_ID:
            raise MailboxOAuthAuthorizationFailedError()
        return
    if configured == "organizations":
        if tenant_id == MSA_TENANT_ID:
            raise MailboxOAuthAuthorizationFailedError()
        return
    if tenant_id != configured:
        raise MailboxOAuthAuthorizationFailedError()


def _parse_granted_scopes(token_response: Mapping[str, Any]) -> tuple[str, ...]:
    raw = token_response.get("scope")
    if raw is None:
        raw = token_response.get("scopes")
    if isinstance(raw, str):
        return _split_scope_value(raw)
    if isinstance(raw, (list, tuple)) and all(isinstance(item, str) for item in raw):
        return tuple(item for item in raw if item)
    return ()


def _split_scope_value(value: str) -> tuple[str, ...]:
    return tuple(part for part in value.replace(",", " ").split() if part)


def _canonical_graph_scope(scope: str) -> str:
    value = scope.strip()
    lower = value.lower()
    if lower.startswith(_GRAPH_SCOPE_PREFIX):
        value = value[len(_GRAPH_SCOPE_PREFIX) :]
    return value.lower()


def _capabilities_from_scopes(
    scopes: tuple[str, ...],
) -> tuple[CommunicationCapability, ...]:
    granted: list[CommunicationCapability] = []
    for scope in scopes:
        capability = _SCOPE_TO_CAPABILITY.get(_canonical_graph_scope(scope))
        if capability is not None:
            granted.append(capability)
    normalized = normalize_communication_capabilities(granted)
    return normalized if normalized is not None else ()


def _expiry_from_token_response(payload: Mapping[str, Any], now: datetime) -> datetime:
    expires_in = payload.get("expires_in")
    if isinstance(expires_in, str) and expires_in.isdigit():
        expires_in = int(expires_in)
    if isinstance(expires_in, bool) or not isinstance(expires_in, int) or expires_in <= 0:
        raise CommunicationCredentialUnavailableError()
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    return now + timedelta(seconds=expires_in)


def _replacement_secret_material(
    stored: _MicrosoftMailboxSecret,
    payload: Mapping[str, Any],
) -> bytes | None:
    rotated = payload.get("refresh_token")
    if not isinstance(rotated, str) or not rotated or rotated == stored.refresh_token:
        return None
    return serialize_microsoft_mailbox_secret(
        refresh_token=rotated,
        scopes=stored.scopes,
        tenant_id=stored.tenant_id,
        object_id=stored.object_id,
    )


def _map_refresh_exception(exc: Exception) -> Exception:
    if isinstance(exc, CommunicationCredentialReauthorizationRequiredError):
        return exc
    if isinstance(exc, CommunicationCredentialUnavailableError):
        return exc
    if _is_transport_failure(exc):
        return CommunicationCredentialUnavailableError()
    return CommunicationCredentialUnavailableError()


def _is_transport_failure(exc: Exception) -> bool:
    if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError, httpx.TransportError)):
        return True
    name = type(exc).__name__
    return name in {
        "ConnectionError",
        "Timeout",
        "TimeoutError",
        "ConnectTimeout",
        "ReadTimeout",
        "ChunkedEncodingError",
        "PyJWKClientConnectionError",
        "PyJWKClientError",
    }


def _is_guid(value: str) -> bool:
    return bool(_GUID_PATTERN.fullmatch(value.strip().lower()))
