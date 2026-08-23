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
from typing import Any
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
from app.domain.models.capabilities import normalize_communication_capabilities
from app.infrastructure.credentials.refresh import RefreshableCredentialResult

logger = get_logger(__name__)

GOOGLE_AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"
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


@dataclass(frozen=True, slots=True)
class _GoogleMailboxSecret:
    refresh_token: str = field(repr=False)
    scopes: tuple[str, ...]
    subject: str

    def __repr__(self) -> str:
        return "_GoogleMailboxSecret(schema_version=1)"


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
        try:
            token_response = self._fetch_token_response(code, code_verifier)
            refresh_token = token_response.get("refresh_token")
            id_token_jwt = token_response.get("id_token")
            if not isinstance(refresh_token, str) or not refresh_token:
                raise MailboxOAuthAuthorizationFailedError()
            if not isinstance(id_token_jwt, str) or not id_token_jwt:
                raise MailboxOAuthAuthorizationFailedError()
            claims = self._verify_id_token(id_token_jwt)
            subject = claims.get("sub")
            if not isinstance(subject, str) or not subject.strip():
                raise MailboxOAuthAuthorizationFailedError()
            granted_scopes = _parse_granted_scopes(token_response)
            capabilities = _capabilities_from_scopes(granted_scopes)
            material = serialize_google_mailbox_secret(
                refresh_token=refresh_token,
                scopes=granted_scopes,
                subject=subject.strip(),
            )
        except MailboxOAuthAuthorizationFailedError:
            logger.warning(
                "gmail_oauth_code_exchange_failed",
                operation="exchange_authorization_code",
                duration_ms=elapsed_ms(started_at),
                error_class="MailboxOAuthAuthorizationFailedError",
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
            logger.warning(
                "gmail_oauth_code_exchange_failed",
                operation="exchange_authorization_code",
                duration_ms=elapsed_ms(started_at),
                error_class=error_class(exc),
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
        try:
            flow = self._new_flow()
            flow.code_verifier = code_verifier
            fetched = flow.fetch_token(code=code, code_verifier=code_verifier)
        except MailboxOAuthAuthorizationFailedError:
            raise
        except Exception as exc:
            if _is_transport_failure(exc):
                raise ServiceUnavailableError(_UNAVAILABLE) from None
            raise MailboxOAuthAuthorizationFailedError() from None
        if not isinstance(fetched, Mapping):
            raise MailboxOAuthAuthorizationFailedError()
        return fetched

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
            from google.auth.transport.requests import Request
            from google.oauth2 import id_token

            claims = id_token.verify_oauth2_token(
                token,
                Request(),
                audience=self._client_id,
            )
        except MailboxOAuthAuthorizationFailedError:
            raise
        except Exception as exc:
            if _is_transport_failure(exc):
                raise ServiceUnavailableError(_UNAVAILABLE) from None
            raise MailboxOAuthAuthorizationFailedError() from None
        if not isinstance(claims, Mapping):
            raise MailboxOAuthAuthorizationFailedError()
        return claims


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
