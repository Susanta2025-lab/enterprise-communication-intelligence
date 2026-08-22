"""Mailbox credential resolution. Secret stores stay inside implementations."""

from app.infrastructure.credentials.environment import (
    EnvironmentCommunicationCredentialResolver,
)

__all__ = ["EnvironmentCommunicationCredentialResolver"]
