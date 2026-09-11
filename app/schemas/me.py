"""Response schemas for the current-user identity endpoint."""

from typing import Literal

from pydantic import BaseModel, Field


class MeResponse(BaseModel):
    """Minimal server-authoritative application identity for the caller.

    Omits internal ``user_id``: the SPA needs only role for presentation.
    Never includes issuer, subject, email, mailbox identity, or tokens.
    """

    application_role: Literal["user", "owner"] = Field(
        description="Persisted ECI application_role for the resolved user.",
        examples=["user"],
    )
    is_owner: bool = Field(
        description="True only when application_role is owner. UX hint only.",
        examples=[False],
    )
