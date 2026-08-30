"""Sanitize presentation-only mailbox identity."""

from app.core.mailbox_display_identity import sanitize_mailbox_display_identity


def test_blank_and_non_string_are_null() -> None:
    assert sanitize_mailbox_display_identity(None) is None
    assert sanitize_mailbox_display_identity("") is None
    assert sanitize_mailbox_display_identity("   ") is None
    assert sanitize_mailbox_display_identity(123) is None


def test_control_characters_and_oversized_values_are_rejected() -> None:
    assert sanitize_mailbox_display_identity("ops\nmailbox@example.com") is None
    assert sanitize_mailbox_display_identity("a" * 321) is None


def test_forbidden_durable_identities_are_rejected() -> None:
    assert (
        sanitize_mailbox_display_identity(
            "google-subject-stable-001",
            forbidden=("google-subject-stable-001",),
        )
        is None
    )
    assert (
        sanitize_mailbox_display_identity(
            "tid:oid",
            forbidden=("tid:oid",),
        )
        is None
    )


def test_trimmed_mailbox_address_is_kept() -> None:
    assert sanitize_mailbox_display_identity("  ops.mailbox@contoso.example  ") == (
        "ops.mailbox@contoso.example"
    )
