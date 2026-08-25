"""Unit tests for exact-account mailbox reauthorization identity checks."""

from uuid import uuid4

import pytest

from app.application.services.mailbox_oauth_reauthorization import load_reauthorization_target
from app.core.exceptions import (
    MailboxOAuthAuthorizationFailedError,
    MailboxOAuthIdentityMismatchError,
)
from app.domain.enums import ConnectorAccountStatus
from tests.support.in_memory_persistence import (
    InMemoryUnitOfWork,
    UnitOfWorkFactory,
    sample_connector_account,
)


def test_identity_mismatch_is_distinct_from_generic_failure() -> None:
    user_id = uuid4()
    account = sample_connector_account(
        user_id,
        provider="gmail",
        external_account_id="google-oidc-sub-bound",
        status=ConnectorAccountStatus.REAUTH_REQUIRED,
    )
    unit = InMemoryUnitOfWork(connector_accounts={account.id: account})
    with pytest.raises(MailboxOAuthIdentityMismatchError) as mismatch:
        load_reauthorization_target(
            UnitOfWorkFactory(unit),
            user_id=user_id,
            connector_account_id=account.id,
            provider="gmail",
            external_account_id="google-oidc-sub-other",
            unavailable_message="unavailable",
        )
    assert isinstance(mismatch.value, MailboxOAuthAuthorizationFailedError)
    assert mismatch.value.message == "Mailbox authorization failed."
    stored = unit.connector_account_store[account.id]
    assert stored.external_account_id == "google-oidc-sub-bound"
    assert stored.status is ConnectorAccountStatus.REAUTH_REQUIRED
