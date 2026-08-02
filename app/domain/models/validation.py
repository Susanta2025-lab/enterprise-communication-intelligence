"""Shared validation helpers for domain models."""


def require_non_empty_text(value: str, field_name: str) -> str:
    """Reject blank text values after trimming surrounding whitespace."""
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized
