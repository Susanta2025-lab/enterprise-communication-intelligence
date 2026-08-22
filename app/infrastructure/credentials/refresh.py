"""Provider-neutral refreshable credential adapter boundary.

Phase 13C and 13D supply concrete Google and Microsoft implementations. This
module does not perform provider HTTP or import vendor OAuth SDKs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class RefreshableCredentialResult:
    """Access token plus optional rotated opaque credential material."""

    access_token: str = field(repr=False)
    expires_at: datetime
    replacement_secret_material: bytes | None = field(default=None, repr=False)

    def __repr__(self) -> str:
        return "RefreshableCredentialResult(expires_at=...)"


class RefreshableCredentialAdapter(Protocol):
    """Acquire a usable access token from stored opaque credential material."""

    def acquire_access_token(
        self,
        *,
        provider: str,
        secret_material: bytes,
    ) -> RefreshableCredentialResult:
        """Return a validated-later access token and optional rotated material.

        Implementations must not log secret material or token contents.
        """
