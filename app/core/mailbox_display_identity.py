"""Presentation-only mailbox identity. Never used as a durable account key."""

from __future__ import annotations

_MAX_LENGTH = 320


def sanitize_mailbox_display_identity(
    value: object,
    *,
    forbidden: tuple[str, ...] = (),
) -> str | None:
    """Return a trimmed human-readable identity, or ``None`` when unsafe.

    Rejects control characters, blank values, oversized strings, and any
    value equal to a durable provider identity supplied in ``forbidden``.
    """
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not candidate or len(candidate) > _MAX_LENGTH:
        return None
    if any(ord(character) < 32 for character in candidate):
        return None
    blocked = {item.strip().lower() for item in forbidden if isinstance(item, str) and item.strip()}
    if candidate.lower() in blocked:
        return None
    return candidate
