"""Attachment security adapters. Scanner binaries stay out of the API image."""

from app.infrastructure.attachments.fake_scanner import FakeAttachmentScanner
from app.infrastructure.attachments.parser import SafeAttachmentParser

__all__ = ["FakeAttachmentScanner", "SafeAttachmentParser"]
