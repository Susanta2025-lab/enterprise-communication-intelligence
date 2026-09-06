"""Attachment security adapters. Scanner binaries stay out of the API image."""

from app.infrastructure.attachments.fake_scanner import FakeAttachmentScanner

__all__ = ["FakeAttachmentScanner"]
