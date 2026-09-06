"""Bounded clamd INSTREAM protocol helpers. No disk, no AV engine.

This module does not import sockets. Scanner I/O lives in the adapter so
protocol mapping can be tested without a daemon.
"""

from __future__ import annotations

import struct

from app.domain.attachment_policy import MAX_ATTACHMENT_CONTENT_BYTES
from app.domain.enums import AttachmentScanVerdict

INSTREAM_COMMAND = b"zINSTREAM\0"
PING_COMMAND = b"zPING\0"
EXPECTED_PONG = b"PONG"
CHUNK_SIZE = 8192
MAX_RESPONSE_BYTES = 512
MAX_SCAN_BYTES = MAX_ATTACHMENT_CONTENT_BYTES


def instream_frames(content: bytes, *, limit: int = MAX_SCAN_BYTES) -> list[bytes]:
    """Return length-prefixed INSTREAM frames, including the terminating zero.

    Raises ``ValueError`` when the payload exceeds the ECI scan limit. The
    adapter maps that to ``ERROR`` and never sends the bytes.
    """
    if len(content) > limit:
        raise ValueError("scan payload exceeds limit")
    frames: list[bytes] = []
    view = memoryview(content)
    offset = 0
    while offset < len(content):
        chunk = view[offset : offset + CHUNK_SIZE]
        frames.append(struct.pack("!I", len(chunk)) + chunk.tobytes())
        offset += len(chunk)
    frames.append(struct.pack("!I", 0))
    return frames


def map_clamd_response(raw: bytes) -> AttachmentScanVerdict:
    """Map a bounded clamd reply to a fail-closed verdict.

    Signature names are discarded. Arbitrary daemon text is not trusted.
    Empty, oversized, or non-ASCII replies are inconclusive, not CLEAN.
    Null terminators from the ``z*`` clamd protocol are stripped.
    """
    if not raw or len(raw) > MAX_RESPONSE_BYTES:
        return AttachmentScanVerdict.UNKNOWN
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError:
        return AttachmentScanVerdict.UNKNOWN
    cleaned = text.strip(" \t\r\n\0")
    if not cleaned:
        return AttachmentScanVerdict.UNKNOWN
    first_line = cleaned.splitlines()[0].strip()
    if not first_line or len(first_line) > 256:
        return AttachmentScanVerdict.UNKNOWN
    if first_line in {"stream: OK", "OK"}:
        return AttachmentScanVerdict.CLEAN
    if first_line.startswith("stream:") and first_line.endswith(" FOUND"):
        return AttachmentScanVerdict.MALICIOUS
    if first_line.endswith(" FOUND"):
        return AttachmentScanVerdict.MALICIOUS
    if first_line.endswith(" ERROR") or first_line.endswith("ERROR"):
        return AttachmentScanVerdict.ERROR
    return AttachmentScanVerdict.UNKNOWN


def is_pong(raw: bytes) -> bool:
    """Return True when a ping reply is the expected PONG token only."""
    return raw.strip(b" \t\r\n\0") == EXPECTED_PONG
