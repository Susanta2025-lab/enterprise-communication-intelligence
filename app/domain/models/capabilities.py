"""Provider-neutral communication capability normalization."""

from collections.abc import Iterable, Sequence

from app.domain.enums import CommunicationCapability

_STABLE_ORDER = tuple(CommunicationCapability)


def normalize_communication_capabilities(
    values: Sequence[str | CommunicationCapability] | None,
) -> tuple[CommunicationCapability, ...] | None:
    """Return a de-duplicated, stably ordered capability tuple.

    ``None`` means capability metadata is unknown (legacy/environment-backed
    accounts). An empty sequence is an explicit empty grant. Unknown values
    raise ``ValueError``. Duplicates are dropped; order follows the enum.
    """
    if values is None:
        return None
    seen: set[CommunicationCapability] = set()
    for item in values:
        capability = (
            item if isinstance(item, CommunicationCapability) else CommunicationCapability(item)
        )
        seen.add(capability)
    return tuple(capability for capability in _STABLE_ORDER if capability in seen)


def serialize_communication_capabilities(
    values: tuple[CommunicationCapability, ...] | None,
) -> list[str] | None:
    """Serialize capabilities for portable JSON storage."""
    normalized = normalize_communication_capabilities(values)
    if normalized is None:
        return None
    return [capability.value for capability in normalized]


def parse_stored_communication_capabilities(
    values: object,
) -> tuple[CommunicationCapability, ...] | None:
    """Rehydrate stored JSON into a normalized capability tuple."""
    if values is None:
        return None
    if not isinstance(values, list):
        raise ValueError("granted_capabilities must be a JSON array or null.")
    items: list[str] = []
    for item in values:
        if not isinstance(item, str):
            raise ValueError("granted_capabilities must contain only strings.")
        items.append(item)
    return normalize_communication_capabilities(items)


def require_requested_communication_capabilities(
    values: Iterable[str | CommunicationCapability],
) -> tuple[CommunicationCapability, ...]:
    """Require an explicit capability list for OAuth authorization sessions."""
    normalized = normalize_communication_capabilities(tuple(values))
    if normalized is None:
        raise ValueError("requested_capabilities must be an explicit list.")
    return normalized
