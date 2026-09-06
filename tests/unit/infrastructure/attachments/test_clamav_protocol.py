"""Offline clamd protocol mapping. No daemon and no malware fixtures."""

import struct

import pytest

from app.domain.attachment_policy import MAX_ATTACHMENT_CONTENT_BYTES
from app.domain.enums import AttachmentScanVerdict
from app.infrastructure.attachments.clamav_protocol import (
    CHUNK_SIZE,
    MAX_RESPONSE_BYTES,
    instream_frames,
    is_pong,
    map_clamd_response,
)


def test_instream_frames_are_length_prefixed_and_terminated() -> None:
    payload = b"clean-pdf-bytes"
    frames = instream_frames(payload)
    body = b"".join(frames)
    assert body.endswith(struct.pack("!I", 0))
    first_len = struct.unpack("!I", body[:4])[0]
    assert first_len == len(payload)
    assert body[4 : 4 + first_len] == payload


def test_instream_frames_chunk_large_payload() -> None:
    payload = b"a" * (CHUNK_SIZE + 20)
    frames = instream_frames(payload)
    assert len(frames) == 3
    assert frames[-1] == struct.pack("!I", 0)


def test_instream_frames_reject_oversize() -> None:
    with pytest.raises(ValueError):
        instream_frames(b"x" * (MAX_ATTACHMENT_CONTENT_BYTES + 1))


def test_map_ok_to_clean() -> None:
    assert map_clamd_response(b"stream: OK\0") is AttachmentScanVerdict.CLEAN
    assert map_clamd_response(b"OK\n") is AttachmentScanVerdict.CLEAN


def test_map_found_to_malicious_without_keeping_signature() -> None:
    raw = b"stream: Win.Test.EICAR_HDB-1 FOUND\0"
    assert map_clamd_response(raw) is AttachmentScanVerdict.MALICIOUS
    assert map_clamd_response(b"Eicar-Test-Signature FOUND") is AttachmentScanVerdict.MALICIOUS


def test_map_error_and_inconclusive() -> None:
    assert map_clamd_response(b"INSTREAM size limit exceeded. ERROR") is AttachmentScanVerdict.ERROR
    assert map_clamd_response(b"stream: UNKNOWN") is AttachmentScanVerdict.UNKNOWN
    assert map_clamd_response(b"") is AttachmentScanVerdict.UNKNOWN
    assert map_clamd_response(b"\xff\xfe") is AttachmentScanVerdict.UNKNOWN
    assert map_clamd_response(b"x" * (MAX_RESPONSE_BYTES + 1)) is AttachmentScanVerdict.UNKNOWN


def test_pong_is_exact() -> None:
    assert is_pong(b"PONG") is True
    assert is_pong(b"PONG\n") is True
    assert is_pong(b"PONG\0") is True
    assert is_pong(b"PONG extra") is False
    assert is_pong(b"PONG\0extra") is False
