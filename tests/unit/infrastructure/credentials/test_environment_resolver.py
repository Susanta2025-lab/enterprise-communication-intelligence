"""Unit tests for environment-backed communication credential resolution."""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from app.core.exceptions import (
    CommunicationCredentialUnavailableError,
    UnsupportedCommunicationCredentialProviderError,
)
from app.domain.interfaces import AccessTokenProvider, CommunicationCredentialResolver
from app.infrastructure.credentials import EnvironmentCommunicationCredentialResolver

_GMAIL_REF = "gmail-demo-account"
_GRAPH_REF = "graph-demo-account"
_SHARED_REF = "account-1"
_GMAIL_ENV = "ECI_COMMUNICATION_CREDENTIAL_GMAIL_GMAIL_DEMO_ACCOUNT_ACCESS_TOKEN"
_GRAPH_ENV = "ECI_COMMUNICATION_CREDENTIAL_MICROSOFT_GRAPH_GRAPH_DEMO_ACCOUNT_ACCESS_TOKEN"
_SHARED_GMAIL_ENV = "ECI_COMMUNICATION_CREDENTIAL_GMAIL_ACCOUNT_1_ACCESS_TOKEN"
_SHARED_GRAPH_ENV = "ECI_COMMUNICATION_CREDENTIAL_MICROSOFT_GRAPH_ACCOUNT_1_ACCESS_TOKEN"
_HYPHEN_ENV = "ECI_COMMUNICATION_CREDENTIAL_GMAIL_A_B_ACCESS_TOKEN"
_GMAIL_TOKEN = "fake-gmail-token"
_GRAPH_TOKEN = "fake-graph-token"
_TEST_TOKEN = "test-access-token"
_SECRET_TOKEN = "SUPER_SECRET_TEST_TOKEN_123"
_UNAVAILABLE = "Communication credential is unavailable."
_UNSUPPORTED = "Communication credential provider is not supported."
_OPAQUE_MARKERS = (
    _GMAIL_TOKEN,
    _GRAPH_TOKEN,
    _TEST_TOKEN,
    _SECRET_TOKEN,
    _GMAIL_ENV,
    _GRAPH_ENV,
    _SHARED_GMAIL_ENV,
    _SHARED_GRAPH_ENV,
    _HYPHEN_ENV,
    _GMAIL_REF,
    _GRAPH_REF,
    _SHARED_REF,
)


def _resolver(
    environ: Mapping[str, str] | None = None,
) -> EnvironmentCommunicationCredentialResolver:
    return EnvironmentCommunicationCredentialResolver(environ=environ or {})


def _assert_error_is_opaque(exc: BaseException) -> None:
    message = getattr(exc, "message", str(exc))
    blob = f"{message}{exc}{exc!r}"
    for marker in _OPAQUE_MARKERS:
        assert marker not in blob
    assert "os.environ" not in blob


def _assert_blob_is_opaque(blob: str) -> None:
    for marker in _OPAQUE_MARKERS:
        assert marker not in blob
    assert "os.environ" not in blob


def test_resolver_implements_domain_port() -> None:
    resolver = _resolver()
    assert isinstance(resolver, CommunicationCredentialResolver)


def test_valid_gmail_ref_resolves_and_returns_token() -> None:
    resolver = _resolver({_GMAIL_ENV: _GMAIL_TOKEN})
    provider: AccessTokenProvider = resolver.resolve(credential_ref=_GMAIL_REF, provider="gmail")
    assert callable(provider)
    assert provider() == _GMAIL_TOKEN


def test_valid_graph_ref_resolves_and_returns_token() -> None:
    resolver = _resolver({_GRAPH_ENV: _GRAPH_TOKEN})
    provider = resolver.resolve(credential_ref=_GRAPH_REF, provider="microsoft_graph")
    assert provider() == _GRAPH_TOKEN


def test_underscore_ref_is_rejected_to_prevent_hyphen_collision() -> None:
    resolver = _resolver({_HYPHEN_ENV: _TEST_TOKEN})
    hyphen = resolver.resolve(credential_ref="a-b", provider="gmail")
    assert hyphen() == _TEST_TOKEN
    with pytest.raises(CommunicationCredentialUnavailableError) as exc_info:
        resolver.resolve(credential_ref="a_b", provider="gmail")
    assert exc_info.value.message == _UNAVAILABLE
    _assert_error_is_opaque(exc_info.value)
    assert "a_b" not in exc_info.value.message
    assert "a-b" not in exc_info.value.message


def test_same_ref_different_providers_use_distinct_secret_keys() -> None:
    resolver = _resolver(
        {
            _SHARED_GMAIL_ENV: _GMAIL_TOKEN,
            _SHARED_GRAPH_ENV: _GRAPH_TOKEN,
        }
    )
    gmail = resolver.resolve(credential_ref=_SHARED_REF, provider="gmail")
    graph = resolver.resolve(credential_ref=_SHARED_REF, provider="microsoft_graph")
    assert gmail() == _GMAIL_TOKEN
    assert graph() == _GRAPH_TOKEN

    gmail_only = _resolver({_SHARED_GMAIL_ENV: _GMAIL_TOKEN})
    assert gmail_only.resolve(credential_ref=_SHARED_REF, provider="gmail")() == _GMAIL_TOKEN
    graph_missing = gmail_only.resolve(credential_ref=_SHARED_REF, provider="microsoft_graph")
    with pytest.raises(CommunicationCredentialUnavailableError):
        graph_missing()


def test_token_lookup_is_on_demand_and_uncached() -> None:
    environ = {_GMAIL_ENV: "token-one"}
    resolver = _resolver(environ)
    provider = resolver.resolve(credential_ref=_GMAIL_REF, provider="gmail")
    assert provider() == "token-one"
    environ[_GMAIL_ENV] = "token-two"
    assert provider() == "token-two"


def test_default_source_is_live_process_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(_GMAIL_ENV, _GMAIL_TOKEN)
    resolver = EnvironmentCommunicationCredentialResolver()
    provider = resolver.resolve(credential_ref=_GMAIL_REF, provider="gmail")
    assert provider() == _GMAIL_TOKEN


def test_blank_reference_is_rejected() -> None:
    resolver = _resolver({_GMAIL_ENV: _GMAIL_TOKEN})
    for value in ("", "   ", "\n", "\t"):
        with pytest.raises(CommunicationCredentialUnavailableError) as exc_info:
            resolver.resolve(credential_ref=value, provider="gmail")
        assert exc_info.value.message == _UNAVAILABLE
        _assert_error_is_opaque(exc_info.value)


def test_none_reference_is_rejected() -> None:
    resolver = _resolver({_GMAIL_ENV: _GMAIL_TOKEN})
    with pytest.raises(CommunicationCredentialUnavailableError) as exc_info:
        resolver.resolve(credential_ref=None, provider="gmail")  # type: ignore[arg-type]
    assert exc_info.value.message == _UNAVAILABLE
    _assert_error_is_opaque(exc_info.value)


@pytest.mark.parametrize(
    "credential_ref",
    [
        "../secrets",
        "gmail demo",
        "gmail=account",
        "gmail;account",
        "gmail$(id)",
        "gmail\naccount",
        "gmail/account",
        "-leading-hyphen",
        "1starts-with-number",
        "a" * 64,
        "gmail_demo",
        "a_b",
        "  gmail-demo-account  ",
        "gmail-demo-account ",
        " gmail-demo-account",
    ],
)
def test_malformed_reference_is_rejected(credential_ref: str) -> None:
    resolver = _resolver({_GMAIL_ENV: _GMAIL_TOKEN})
    with pytest.raises(CommunicationCredentialUnavailableError) as exc_info:
        resolver.resolve(credential_ref=credential_ref, provider="gmail")
    assert exc_info.value.message == _UNAVAILABLE
    _assert_error_is_opaque(exc_info.value)
    assert credential_ref not in exc_info.value.message


def test_unknown_reference_fails_on_token_invocation() -> None:
    resolver = _resolver({_GMAIL_ENV: _GMAIL_TOKEN})
    provider = resolver.resolve(credential_ref="unknown-demo-account", provider="gmail")
    with pytest.raises(CommunicationCredentialUnavailableError) as exc_info:
        provider()
    assert exc_info.value.message == _UNAVAILABLE
    _assert_error_is_opaque(exc_info.value)
    assert "unknown-demo-account" not in exc_info.value.message
    assert "UNKNOWN_DEMO_ACCOUNT" not in str(exc_info.value)


def test_configured_secret_missing_fails_on_token_invocation() -> None:
    resolver = _resolver({})
    provider = resolver.resolve(credential_ref=_GMAIL_REF, provider="gmail")
    with pytest.raises(CommunicationCredentialUnavailableError) as exc_info:
        provider()
    assert exc_info.value.message == _UNAVAILABLE
    _assert_error_is_opaque(exc_info.value)


@pytest.mark.parametrize("raw", ["", "   ", "\n\t"])
def test_blank_configured_token_is_rejected(raw: str) -> None:
    resolver = _resolver({_GMAIL_ENV: raw})
    provider = resolver.resolve(credential_ref=_GMAIL_REF, provider="gmail")
    with pytest.raises(CommunicationCredentialUnavailableError) as exc_info:
        provider()
    assert exc_info.value.message == _UNAVAILABLE
    _assert_error_is_opaque(exc_info.value)


def test_token_surrounding_whitespace_is_stripped() -> None:
    resolver = _resolver({_GMAIL_ENV: f"  {_TEST_TOKEN}  "})
    provider = resolver.resolve(credential_ref=_GMAIL_REF, provider="gmail")
    assert provider() == _TEST_TOKEN


def test_fake_provider_is_unsupported() -> None:
    resolver = _resolver({_GMAIL_ENV: _GMAIL_TOKEN})
    with pytest.raises(UnsupportedCommunicationCredentialProviderError) as exc_info:
        resolver.resolve(credential_ref=_GMAIL_REF, provider="fake")
    assert exc_info.value.message == _UNSUPPORTED
    _assert_error_is_opaque(exc_info.value)
    assert "fake" not in exc_info.value.message.lower()


@pytest.mark.parametrize("provider", ["", "   ", "unknown", "google", "azure", "AWS"])
def test_unsupported_or_blank_provider_is_rejected(provider: str) -> None:
    resolver = _resolver({_GMAIL_ENV: _GMAIL_TOKEN})
    with pytest.raises(UnsupportedCommunicationCredentialProviderError) as exc_info:
        resolver.resolve(credential_ref=_GMAIL_REF, provider=provider)
    assert exc_info.value.message == _UNSUPPORTED
    _assert_error_is_opaque(exc_info.value)


def test_provider_is_normalized_case_insensitively() -> None:
    resolver = _resolver({_GMAIL_ENV: _GMAIL_TOKEN, _GRAPH_ENV: _GRAPH_TOKEN})
    gmail = resolver.resolve(credential_ref=_GMAIL_REF, provider=" Gmail ")
    graph = resolver.resolve(credential_ref=_GRAPH_REF, provider="Microsoft_Graph")
    assert gmail() == _GMAIL_TOKEN
    assert graph() == _GRAPH_TOKEN


def test_repr_and_str_do_not_expose_token_or_locator() -> None:
    resolver = _resolver({_GMAIL_ENV: _SECRET_TOKEN})
    provider = resolver.resolve(credential_ref=_GMAIL_REF, provider="gmail")
    blob = f"{resolver!r}{resolver}{provider!r}{provider}"
    _assert_blob_is_opaque(blob)
    assert "EnvironmentCommunicationCredentialResolver()" in repr(resolver)


def test_unknown_ref_error_does_not_enumerate_configured_refs() -> None:
    resolver = _resolver({_GMAIL_ENV: _GMAIL_TOKEN, _GRAPH_ENV: _GRAPH_TOKEN})
    provider = resolver.resolve(credential_ref="missing-account", provider="gmail")
    with pytest.raises(CommunicationCredentialUnavailableError) as exc_info:
        provider()
    blob = f"{exc_info.value.message}{exc_info.value!r}"
    _assert_blob_is_opaque(blob)
    assert "gmail-demo" not in blob
    assert "graph-demo" not in blob
    assert "configured" not in blob.lower()
    assert _GMAIL_ENV not in blob
    assert _GRAPH_ENV not in blob


def test_secret_token_never_appears_in_exceptions_or_logs(log_events: list[dict]) -> None:
    resolver = _resolver({_GMAIL_ENV: _SECRET_TOKEN})
    provider = resolver.resolve(credential_ref=_GMAIL_REF, provider="gmail")
    assert provider() == _SECRET_TOKEN
    with pytest.raises(UnsupportedCommunicationCredentialProviderError) as unsupported:
        resolver.resolve(credential_ref=_GMAIL_REF, provider="unknown")
    with pytest.raises(CommunicationCredentialUnavailableError) as malformed:
        resolver.resolve(credential_ref="a_b", provider="gmail")
    blank = _resolver({_GMAIL_ENV: "   "})
    blank_provider = blank.resolve(credential_ref=_GMAIL_REF, provider="gmail")
    with pytest.raises(CommunicationCredentialUnavailableError) as blank_exc:
        blank_provider()
    blob = (
        f"{unsupported.value}{unsupported.value!r}{malformed.value}{malformed.value!r}"
        f"{blank_exc.value}{blank_exc.value!r}{resolver!r}{provider!r}{log_events!r}"
    )
    _assert_blob_is_opaque(blob)


def test_logs_omit_secrets_and_locators(log_events: list[dict]) -> None:
    resolver = _resolver({_GMAIL_ENV: _SECRET_TOKEN})
    provider = resolver.resolve(credential_ref=_GMAIL_REF, provider="gmail")
    assert provider() == _SECRET_TOKEN
    with pytest.raises(CommunicationCredentialUnavailableError):
        resolver.resolve(credential_ref="bad ref", provider="gmail")
    with pytest.raises(UnsupportedCommunicationCredentialProviderError):
        resolver.resolve(credential_ref=_GMAIL_REF, provider="fake")
    missing = _resolver({})
    missing_provider = missing.resolve(credential_ref=_GMAIL_REF, provider="gmail")
    with pytest.raises(CommunicationCredentialUnavailableError):
        missing_provider()
    blank = _resolver({_GMAIL_ENV: "\n"})
    blank_provider = blank.resolve(credential_ref=_GMAIL_REF, provider="gmail")
    with pytest.raises(CommunicationCredentialUnavailableError):
        blank_provider()
    blob = repr(log_events)
    _assert_blob_is_opaque(blob)
    assert "bad ref" not in blob
    assert "authorization" not in blob.lower()
    assert any(
        event.get("event") == "communication_credential_resolution_failed" for event in log_events
    )
    assert any(event.get("event") == "communication_credential_unavailable" for event in log_events)
    assert any(event.get("resolver_backend") == "environment" for event in log_events)
    assert any(event.get("provider") == "gmail" for event in log_events)
    assert not any(event.get("credential_ref") for event in log_events)
    assert not any("ACCESS_TOKEN" in str(event) for event in log_events)
