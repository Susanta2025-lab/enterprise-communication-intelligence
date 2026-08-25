"""Google OAuth and Gmail refresh adapters.

Google SDK types stay inside this module. Application and domain layers receive
provider-neutral URLs, capabilities, and opaque secret bytes only.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, TypeGuard
from urllib.parse import parse_qs, urlparse

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
from app.domain.interfaces.mailbox_token_revoker import MailboxTokenRevoker
from app.domain.models.capabilities import normalize_communication_capabilities
from app.infrastructure.credentials.refresh import RefreshableCredentialResult

logger = get_logger(__name__)

GOOGLE_AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE_URI = "https://oauth2.googleapis.com/revoke"
_SAFE_OAUTH_ERRORS = frozenset(
    {
        "access_denied",
        "invalid_client",
        "invalid_grant",
        "invalid_request",
        "invalid_scope",
        "redirect_uri_mismatch",
        "server_error",
        "temporarily_unavailable",
        "unauthorized_client",
        "unsupported_grant_type",
    }
)
GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
OPENID_SCOPE = "openid"
REQUESTED_GMAIL_OAUTH_SCOPES: tuple[str, ...] = (
    OPENID_SCOPE,
    GMAIL_READONLY_SCOPE,
    GMAIL_SEND_SCOPE,
)
_FORBIDDEN_SCOPES = frozenset(
    {
        "profile",
        "email",
        "https://mail.google.com/",
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/gmail.compose",
    }
)
_SCOPE_TO_CAPABILITY = {
    GMAIL_READONLY_SCOPE: CommunicationCapability.MAIL_READ,
    GMAIL_SEND_SCOPE: CommunicationCapability.MAIL_SEND,
}
_MATERIAL_VERSION = 1
_PROVIDER = "gmail"
_UNAVAILABLE = "Gmail mailbox authorization is unavailable."
_CODE_CHALLENGE_METHOD = "S256"

TokenFetcher = Callable[[str, str], Mapping[str, Any]]
IdTokenVerifier = Callable[[str], Mapping[str, Any]]
RefreshTransportFactory = Callable[[], Any]
RevokeTransport = Callable[[str], None]


@dataclass(frozen=True, slots=True)
class _GoogleMailboxSecret:
    refresh_token: str = field(repr=False)
    scopes: tuple[str, ...]
    subject: str

    def __repr__(self) -> str:
        return "_GoogleMailboxSecret(schema_version=1)"


@dataclass(slots=True)
class _TokenExchangeDiagnostics:
    oauth_error: str | None = None
    refresh_token_present: bool = False
    id_token_present: bool = False


class GoogleMailboxOAuthClient(MailboxOAuthClient):
    """Confidential web-server Google authorization-code client."""

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        token_fetcher: TokenFetcher | None = None,
        id_token_verifier: IdTokenVerifier | None = None,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._token_fetcher = token_fetcher
        self._id_token_verifier = id_token_verifier

    def __repr__(self) -> str:
        return "GoogleMailboxOAuthClient()"

    def build_authorization_url(
        self,
        *,
        state: str,
        code_challenge: str,
        code_challenge_method: str,
    ) -> str:
        """Build a Google authorization URL using the Phase 13A state and PKCE."""
        started_at = time.perf_counter()
        if not state or not code_challenge or code_challenge_method != _CODE_CHALLENGE_METHOD:
            raise MailboxOAuthAuthorizationFailedError()
        try:
            flow = self._new_flow()
            url, returned_state = flow.authorization_url(
                state=state,
                code_challenge=code_challenge,
                code_challenge_method=_CODE_CHALLENGE_METHOD,
                access_type="offline",
                prompt="consent",
                include_granted_scopes="true",
            )
        except MailboxOAuthAuthorizationFailedError:
            raise
        except Exception as exc:
            logger.warning(
                "gmail_oauth_authorization_url_failed",
                operation="build_authorization_url",
                duration_ms=elapsed_ms(started_at),
                error_class=error_class(exc),
            )
            raise MailboxOAuthAuthorizationFailedError() from None
        if returned_state != state or not _url_matches_session(
            url,
            state=state,
            code_challenge=code_challenge,
            redirect_uri=self._redirect_uri,
            client_id=self._client_id,
        ):
            logger.warning(
                "gmail_oauth_authorization_url_rejected",
                operation="build_authorization_url",
                duration_ms=elapsed_ms(started_at),
                error_class="AuthorizationUrlMismatch",
            )
            raise MailboxOAuthAuthorizationFailedError()
        logger.info(
            "gmail_oauth_authorization_url_built",
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
        diagnostics = _TokenExchangeDiagnostics()
        try:
            token_response = self._fetch_token_response(code, code_verifier, diagnostics)
            _record_token_presence(diagnostics, token_response)
            refresh_token = token_response.get("refresh_token")
            id_token_jwt = token_response.get("id_token")
            if not isinstance(refresh_token, str) or not refresh_token:
                raise MailboxOAuthAuthorizationFailedError()
            if not isinstance(id_token_jwt, str) or not id_token_jwt:
                raise MailboxOAuthAuthorizationFailedError()
            claims = self._verify_id_token(
                id_token_jwt,
                started_at=started_at,
                diagnostics=diagnostics,
            )
            subject = claims.get("sub")
            if not _verified_subject_present(subject):
                _log_id_token_verify_failed(
                    started_at=started_at,
                    diagnostics=diagnostics,
                    verify_error_class="MailboxOAuthAuthorizationFailedError",
                    subject_present=False,
                    issuer_present=_verified_claim_present(claims.get("iss")),
                    audience_present=_verified_claim_present(claims.get("aud")),
                )
                raise MailboxOAuthAuthorizationFailedError()
            granted_scopes = _parse_granted_scopes(token_response)
            capabilities = _capabilities_from_scopes(granted_scopes)
            material = serialize_google_mailbox_secret(
                refresh_token=refresh_token,
                scopes=granted_scopes,
                subject=subject.strip(),
            )
        except MailboxOAuthAuthorizationFailedError:
            _log_code_exchange_failed(
                started_at=started_at,
                error_class_name="MailboxOAuthAuthorizationFailedError",
                diagnostics=diagnostics,
            )
            raise
        except ServiceUnavailableError:
            logger.warning(
                "gmail_oauth_code_exchange_unavailable",
                operation="exchange_authorization_code",
                duration_ms=elapsed_ms(started_at),
                error_class="ServiceUnavailableError",
            )
            raise
        except Exception as exc:
            if _is_transport_failure(exc):
                logger.warning(
                    "gmail_oauth_code_exchange_unavailable",
                    operation="exchange_authorization_code",
                    duration_ms=elapsed_ms(started_at),
                    error_class=error_class(exc),
                )
                raise ServiceUnavailableError(_UNAVAILABLE) from None
            _log_code_exchange_failed(
                started_at=started_at,
                error_class_name=error_class(exc),
                diagnostics=diagnostics,
            )
            raise MailboxOAuthAuthorizationFailedError() from None
        logger.info(
            "gmail_oauth_code_exchanged",
            operation="exchange_authorization_code",
            duration_ms=elapsed_ms(started_at),
        )
        return MailboxOAuthAuthorizationResult(
            external_account_id=subject.strip(),
            granted_capabilities=capabilities,
            secret_material=material,
        )

    def _new_flow(self) -> Any:
        from google_auth_oauthlib.flow import Flow

        return Flow.from_client_config(
            {
                "web": {
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "auth_uri": GOOGLE_AUTH_URI,
                    "token_uri": GOOGLE_TOKEN_URI,
                }
            },
            scopes=list(REQUESTED_GMAIL_OAUTH_SCOPES),
            redirect_uri=self._redirect_uri,
            autogenerate_code_verifier=False,
        )

    def _fetch_token_response(
        self,
        code: str,
        code_verifier: str,
        diagnostics: _TokenExchangeDiagnostics,
    ) -> Mapping[str, Any]:
        if self._token_fetcher is not None:
            try:
                fetched = self._token_fetcher(code, code_verifier)
            except MailboxOAuthAuthorizationFailedError:
                raise
            except ServiceUnavailableError:
                raise
            except Exception as exc:
                _record_oauth_error(diagnostics, exc)
                if _is_transport_failure(exc):
                    raise ServiceUnavailableError(_UNAVAILABLE) from None
                raise MailboxOAuthAuthorizationFailedError() from None
            if not isinstance(fetched, Mapping):
                raise MailboxOAuthAuthorizationFailedError()
            return fetched
        try:
            flow = self._new_flow()
            flow.code_verifier = code_verifier
            fetched = flow.fetch_token(code=code, code_verifier=code_verifier)
        except MailboxOAuthAuthorizationFailedError:
            raise
        except Exception as exc:
            _record_oauth_error(diagnostics, exc)
            if _is_transport_failure(exc):
                raise ServiceUnavailableError(_UNAVAILABLE) from None
            raise MailboxOAuthAuthorizationFailedError() from None
        if not isinstance(fetched, Mapping):
            raise MailboxOAuthAuthorizationFailedError()
        return fetched

    def _verify_id_token(
        self,
        token: str,
        *,
        started_at: float,
        diagnostics: _TokenExchangeDiagnostics,
    ) -> Mapping[str, Any]:
        try:
            claims = self._id_token_claims(token)
        except MailboxOAuthAuthorizationFailedError:
            _log_id_token_verify_failed(
                started_at=started_at,
                diagnostics=diagnostics,
                verify_error_class="MailboxOAuthAuthorizationFailedError",
                subject_present=False,
            )
            raise
        except ServiceUnavailableError:
            raise
        except Exception as exc:
            if _is_transport_failure(exc):
                raise ServiceUnavailableError(_UNAVAILABLE) from None
            _log_id_token_verify_failed(
                started_at=started_at,
                diagnostics=diagnostics,
                verify_error_class=error_class(exc),
                subject_present=False,
            )
            raise MailboxOAuthAuthorizationFailedError() from None
        if not isinstance(claims, Mapping):
            _log_id_token_verify_failed(
                started_at=started_at,
                diagnostics=diagnostics,
                verify_error_class="MailboxOAuthAuthorizationFailedError",
                subject_present=False,
            )
            raise MailboxOAuthAuthorizationFailedError()
        return claims

    def _id_token_claims(self, token: str) -> Mapping[str, Any]:
        if self._id_token_verifier is not None:
            return self._id_token_verifier(token)
        from google.auth.transport.requests import Request
        from google.oauth2 import id_token

        return id_token.verify_oauth2_token(
            token,
            Request(),
            audience=self._client_id,
        )


class GoogleMailboxTokenRevoker(MailboxTokenRevoker):
    """Revoke the Google grant encoded in stored Gmail secret material.

    This is scoped to the refresh token issued to this ECI application. It is
    not a Google-account-wide session revocation. Remote failure is raised to
    the caller; disconnect treats it as best-effort after local credential
    removal.
    """

    def __init__(self, *, transport: RevokeTransport | None = None) -> None:
        self._transport = transport

    def __repr__(self) -> str:
        return "GoogleMailboxTokenRevoker()"

    def revoke(self, secret_material: bytes) -> None:
        """POST the stored refresh token to Google's token revocation endpoint."""
        started_at = time.perf_counter()
        stored = deserialize_google_mailbox_secret(secret_material)
        try:
            if self._transport is not None:
                self._transport(stored.refresh_token)
            else:
                _post_google_revoke(stored.refresh_token)
        except CommunicationCredentialUnavailableError:
            logger.warning(
                "gmail_oauth_token_revoke_unavailable",
                operation="revoke",
                duration_ms=elapsed_ms(started_at),
                error_class="CommunicationCredentialUnavailableError",
            )
            raise
        except Exception as exc:
            logger.warning(
                "gmail_oauth_token_revoke_unavailable",
                operation="revoke",
                duration_ms=elapsed_ms(started_at),
                error_class=error_class(exc),
            )
            raise CommunicationCredentialUnavailableError() from None
        logger.info(
            "gmail_oauth_token_revoked",
            operation="revoke",
            duration_ms=elapsed_ms(started_at),
        )


class GoogleRefreshableCredentialAdapter:
    """Refresh Gmail access tokens from stored Google secret material."""

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        request_factory: RefreshTransportFactory | None = None,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._request_factory = request_factory

    def __repr__(self) -> str:
        return "GoogleRefreshableCredentialAdapter()"

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
            stored = deserialize_google_mailbox_secret(secret_material)
            credentials = _google_refresh_credentials(
                refresh_token=stored.refresh_token,
                scopes=stored.scopes,
                client_id=self._client_id,
                client_secret=self._client_secret,
            )
            request = self._request_factory() if self._request_factory is not None else None
            if request is None:
                from google.auth.transport.requests import Request

                request = Request()
            credentials.refresh(request)
            token = credentials.token
            expiry = credentials.expiry
            if not isinstance(token, str) or not token.strip():
                raise CommunicationCredentialUnavailableError()
            if not isinstance(expiry, datetime):
                raise CommunicationCredentialUnavailableError()
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=UTC)
            replacement = _replacement_secret_material(stored, credentials)
            logger.info(
                "gmail_oauth_access_token_refreshed",
                operation="acquire_access_token",
                duration_ms=elapsed_ms(started_at),
            )
            return RefreshableCredentialResult(
                access_token=token.strip(),
                expires_at=expiry,
                replacement_secret_material=replacement,
            )
        except CommunicationCredentialReauthorizationRequiredError:
            logger.warning(
                "gmail_oauth_refresh_reauthorization_required",
                operation="acquire_access_token",
                duration_ms=elapsed_ms(started_at),
                error_class="CommunicationCredentialReauthorizationRequiredError",
            )
            raise
        except CommunicationCredentialUnavailableError:
            logger.warning(
                "gmail_oauth_refresh_unavailable",
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
                "gmail_oauth_refresh_unavailable",
                operation="acquire_access_token",
                duration_ms=elapsed_ms(started_at),
                error_class=error_class(mapped),
            )
            raise mapped from None


def serialize_google_mailbox_secret(
    *,
    refresh_token: str,
    scopes: tuple[str, ...],
    subject: str,
) -> bytes:
    """Serialize Google-private refresh material. Omits access and ID tokens."""
    payload = {
        "v": _MATERIAL_VERSION,
        "rt": refresh_token,
        "sc": list(scopes),
        "sub": subject,
    }
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")


def deserialize_google_mailbox_secret(secret_material: bytes) -> _GoogleMailboxSecret:
    """Parse stored Google refresh material or raise unavailability."""
    if not isinstance(secret_material, bytes) or not secret_material:
        raise CommunicationCredentialUnavailableError()
    try:
        payload = json.loads(secret_material.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise CommunicationCredentialUnavailableError() from None
    if not isinstance(payload, dict) or payload.get("v") != _MATERIAL_VERSION:
        raise CommunicationCredentialUnavailableError()
    refresh_token = payload.get("rt")
    subject = payload.get("sub")
    scopes_value = payload.get("sc")
    if not isinstance(refresh_token, str) or not refresh_token:
        raise CommunicationCredentialUnavailableError()
    if not isinstance(subject, str) or not subject.strip():
        raise CommunicationCredentialUnavailableError()
    if not isinstance(scopes_value, list) or not all(
        isinstance(item, str) and item for item in scopes_value
    ):
        raise CommunicationCredentialUnavailableError()
    return _GoogleMailboxSecret(
        refresh_token=refresh_token,
        scopes=tuple(scopes_value),
        subject=subject.strip(),
    )


def _post_google_revoke(refresh_token: str) -> None:
    import urllib.error
    import urllib.parse
    import urllib.request

    payload = urllib.parse.urlencode({"token": refresh_token}).encode("ascii")
    request = urllib.request.Request(
        GOOGLE_REVOKE_URI,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            status = int(getattr(response, "status", 200))
    except TimeoutError:
        raise CommunicationCredentialUnavailableError() from None
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        if status >= 500:
            raise CommunicationCredentialUnavailableError() from None
        if status >= 400:
            return
        raise CommunicationCredentialUnavailableError() from None
    except urllib.error.URLError:
        raise CommunicationCredentialUnavailableError() from None
    if status >= 500:
        raise CommunicationCredentialUnavailableError()
    if status >= 400:
        return
    if status < 200 or status >= 300:
        raise CommunicationCredentialUnavailableError()


def _google_refresh_credentials(
    *,
    refresh_token: str,
    scopes: tuple[str, ...],
    client_id: str,
    client_secret: str,
) -> Any:
    from google.oauth2.credentials import Credentials

    return Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri=GOOGLE_TOKEN_URI,
        client_id=client_id,
        client_secret=client_secret,
        scopes=list(scopes),
    )


def _replacement_secret_material(
    stored: _GoogleMailboxSecret,
    credentials: Any,
) -> bytes | None:
    rotated = getattr(credentials, "refresh_token", None)
    if not isinstance(rotated, str) or not rotated or rotated == stored.refresh_token:
        return None
    return serialize_google_mailbox_secret(
        refresh_token=rotated,
        scopes=stored.scopes,
        subject=stored.subject,
    )


def _map_refresh_exception(exc: Exception) -> Exception:
    from google.auth.exceptions import RefreshError, TransportError

    if isinstance(exc, TransportError) or _is_transport_failure(exc):
        return CommunicationCredentialUnavailableError()
    if isinstance(exc, RefreshError) and _is_confirmed_invalid_grant(exc):
        return CommunicationCredentialReauthorizationRequiredError()
    if isinstance(exc, CommunicationCredentialReauthorizationRequiredError):
        return exc
    if isinstance(exc, CommunicationCredentialUnavailableError):
        return exc
    return CommunicationCredentialUnavailableError()


def _is_confirmed_invalid_grant(exc: Exception) -> bool:
    if getattr(exc, "retryable", False):
        return False
    if len(exc.args) < 2 or not isinstance(exc.args[1], dict):
        return False
    return exc.args[1].get("error") == "invalid_grant"


def _is_transport_failure(exc: Exception) -> bool:
    from google.auth.exceptions import TransportError

    if isinstance(exc, TransportError):
        return True
    name = type(exc).__name__
    return name in {
        "ConnectionError",
        "Timeout",
        "TimeoutError",
        "ConnectTimeout",
        "ReadTimeout",
        "ChunkedEncodingError",
    }


def _log_code_exchange_failed(
    *,
    started_at: float,
    error_class_name: str,
    diagnostics: _TokenExchangeDiagnostics,
) -> None:
    logger.warning(
        "gmail_oauth_code_exchange_failed",
        operation="exchange_authorization_code",
        provider=_PROVIDER,
        duration_ms=elapsed_ms(started_at),
        error_class=error_class_name,
        oauth_error=diagnostics.oauth_error,
        refresh_token_present=diagnostics.refresh_token_present,
        id_token_present=diagnostics.id_token_present,
    )


def _log_id_token_verify_failed(
    *,
    started_at: float,
    diagnostics: _TokenExchangeDiagnostics,
    verify_error_class: str,
    subject_present: bool,
    issuer_present: bool | None = None,
    audience_present: bool | None = None,
) -> None:
    fields: dict[str, object] = {
        "provider": _PROVIDER,
        "operation": "verify_id_token",
        "duration_ms": elapsed_ms(started_at),
        "verify_error_class": verify_error_class,
        "subject_present": subject_present,
        "oauth_error": diagnostics.oauth_error,
        "refresh_token_present": diagnostics.refresh_token_present,
        "id_token_present": diagnostics.id_token_present,
    }
    if issuer_present is not None:
        fields["issuer_present"] = issuer_present
    if audience_present is not None:
        fields["audience_present"] = audience_present
    logger.warning("gmail_oauth_id_token_verify_failed", **fields)


def _verified_subject_present(value: object) -> TypeGuard[str]:
    return isinstance(value, str) and bool(value.strip())


def _verified_claim_present(value: object) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple)):
        return any(isinstance(item, str) and item.strip() for item in value)
    return False


def _record_token_presence(
    diagnostics: _TokenExchangeDiagnostics,
    token_response: Mapping[str, Any],
) -> None:
    diagnostics.refresh_token_present = _nonempty_string_present(
        token_response.get("refresh_token")
    )
    diagnostics.id_token_present = _nonempty_string_present(token_response.get("id_token"))
    if diagnostics.oauth_error is None:
        diagnostics.oauth_error = _safe_oauth_error_value(token_response.get("error"))


def _record_oauth_error(diagnostics: _TokenExchangeDiagnostics, exc: BaseException) -> None:
    if diagnostics.oauth_error is None:
        diagnostics.oauth_error = _oauth_error_from_exception(exc)


def _oauth_error_from_exception(exc: BaseException) -> str | None:
    sanitized = _safe_oauth_error_value(getattr(exc, "error", None))
    if sanitized is not None:
        return sanitized
    for arg in exc.args:
        if isinstance(arg, Mapping):
            sanitized = _safe_oauth_error_value(arg.get("error"))
            if sanitized is not None:
                return sanitized
    payload = _json_object_from_response(getattr(exc, "response", None))
    if payload is None:
        return None
    return _safe_oauth_error_value(payload.get("error"))


def _json_object_from_response(response: Any) -> Mapping[str, Any] | None:
    if response is None:
        return None
    reader = getattr(response, "json", None)
    if not callable(reader):
        return None
    try:
        payload = reader()
    except Exception:
        return None
    if isinstance(payload, Mapping):
        return payload
    return None


def _safe_oauth_error_value(raw: object) -> str | None:
    if not isinstance(raw, str):
        return None
    candidate = raw.strip().lower()
    if candidate not in _SAFE_OAUTH_ERRORS:
        return None
    return candidate


def _nonempty_string_present(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def _url_matches_session(
    url: str,
    *,
    state: str,
    code_challenge: str,
    redirect_uri: str,
    client_id: str,
) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
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
    if params.get("access_type") != ["offline"]:
        return False
    if params.get("prompt") != ["consent"]:
        return False
    if params.get("include_granted_scopes") != ["true"]:
        return False
    if params.get("response_type") != ["code"]:
        return False
    scopes = _split_scope_value(params.get("scope", [""])[0])
    if set(REQUESTED_GMAIL_OAUTH_SCOPES) - set(scopes):
        return False
    if set(scopes) & _FORBIDDEN_SCOPES:
        return False
    return True


def _parse_granted_scopes(token_response: Mapping[str, Any]) -> tuple[str, ...]:
    raw = token_response.get("scope")
    if raw is None:
        raw = token_response.get("scopes")
    if isinstance(raw, str):
        scopes = _split_scope_value(raw)
    elif isinstance(raw, (list, tuple)) and all(isinstance(item, str) for item in raw):
        scopes = tuple(item for item in raw if item)
    else:
        return ()
    return scopes


def _split_scope_value(value: str) -> tuple[str, ...]:
    return tuple(part for part in value.replace(",", " ").split() if part)


def _capabilities_from_scopes(
    scopes: tuple[str, ...],
) -> tuple[CommunicationCapability, ...]:
    granted: list[CommunicationCapability] = []
    for scope in scopes:
        capability = _SCOPE_TO_CAPABILITY.get(scope)
        if capability is not None:
            granted.append(capability)
    normalized = normalize_communication_capabilities(granted)
    return normalized if normalized is not None else ()
