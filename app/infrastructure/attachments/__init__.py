"""Attachment security adapters. Scanner binaries stay out of the API image."""

from app.infrastructure.attachments.fake_scanner import FakeAttachmentScanner
from app.infrastructure.attachments.parser import SafeAttachmentParser
from app.infrastructure.attachments.scanner_factory import create_attachment_scanner
from app.infrastructure.attachments.unavailable_scanner import UnavailableAttachmentScanner

__all__ = [
    "FakeAttachmentScanner",
    "SafeAttachmentParser",
    "UnavailableAttachmentScanner",
    "create_attachment_scanner",
]
