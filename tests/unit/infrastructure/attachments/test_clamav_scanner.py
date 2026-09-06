"""ClamAV adapter tests use a fake socket. No daemon and no malware files."""

from __future__ import annotations

import socket

from app.domain.attachment_policy import MAX_ATTACHMENT_CONTENT_BYTES
from app.domain.enums import AttachmentScanVerdict
from app.domain.interfaces.attachment_scanner import AttachmentScanResult
from app.infrastructure.attachments.clamav_protocol import INSTREAM_COMMAND, PING_COMMAND
from app.infrastructure.attachments.clamav_scanner import ClamAVAttachmentScanner
from tests.unit.infrastructure.attachments.fixtures import attachment_content, pdf_with_text


class _FakeSocket:
    def __init__(self, replies: list[bytes], *, fail_send: bool = False) -> None:
        self.replies = list(replies)
        self.sent = bytearray()
        self.closed = False
        self.shutdown_called = False
        self.timeout: float | None = None
        self._fail_send = fail_send

    def settimeout(self, value: float) -> None:
        self.timeout = value

    def sendall(self, data: bytes) -> None:
        if self._fail_send:
            raise TimeoutError("timed out")
        self.sent.extend(data)

    def recv(self, size: int) -> bytes:
        if not self.replies:
            return b""
        current = self.replies[0]
        chunk = current[:size]
        remainder = current[size:]
        if remainder:
            self.replies[0] = remainder
        else:
            self.replies.pop(0)
        return chunk

    def shutdown(self, _how: int) -> None:
        self.shutdown_called = True

    def close(self) -> None:
        self.closed = True


def _scanner(sock: _FakeSocket) -> ClamAVAttachmentScanner:
    return ClamAVAttachmentScanner(
        "scanner.internal",
        3310,
        2.0,
        socket_factory=lambda: sock,
    )


def _pdf() -> bytes:
    return pdf_with_text("ordinary quarterly notes")


def _content(payload: bytes | None = None):
    return attachment_content(
        payload if payload is not None else _pdf(),
        filename="report.pdf",
        media_type="application/pdf",
    )


def test_ok_response_is_clean_and_closes() -> None:
    sock = _FakeSocket([b"stream: OK\0"])
    result = _scanner(sock).scan(_content())
    assert result.verdict is AttachmentScanVerdict.CLEAN
    assert sock.sent.startswith(INSTREAM_COMMAND)
    assert sock.closed is True
    assert sock.shutdown_called is True
    assert "scanner.internal" not in result.model_dump_json()


def test_found_response_is_malicious_without_signature_field() -> None:
    sock = _FakeSocket([b"stream: Win.Test.EICAR_HDB-1 FOUND\0"])
    result = _scanner(sock).scan(_content())
    assert result.verdict is AttachmentScanVerdict.MALICIOUS
    dumped = result.model_dump()
    assert dumped == {"verdict": "malicious"}
    assert "EICAR" not in str(dumped)


def test_unexpected_response_is_unknown() -> None:
    sock = _FakeSocket([b"stream: maybe later"])
    result = _scanner(sock).scan(_content())
    assert result.verdict is AttachmentScanVerdict.UNKNOWN


def test_timeout_and_refused_are_error_never_clean() -> None:
    timeout_sock = _FakeSocket([], fail_send=True)
    timeout_result = _scanner(timeout_sock).scan(_content())
    assert timeout_result.verdict is AttachmentScanVerdict.ERROR

    def _refused() -> socket.socket:
        raise ConnectionRefusedError("connection refused")

    refused = ClamAVAttachmentScanner("scanner.internal", 3310, 1.0, socket_factory=_refused)
    result = refused.scan(_content())
    assert result.verdict is AttachmentScanVerdict.ERROR


def test_oversize_payload_is_error_without_socket() -> None:
    called = False

    def _factory() -> socket.socket:
        nonlocal called
        called = True
        raise AssertionError("socket must not open for oversized input")

    scanner = ClamAVAttachmentScanner("scanner.internal", 3310, 1.0, socket_factory=_factory)
    payload = b"%PDF-1.4\n" + (b"A" * MAX_ATTACHMENT_CONTENT_BYTES)
    result = scanner.scan(_content(payload[: MAX_ATTACHMENT_CONTENT_BYTES + 1]))
    assert result.verdict is AttachmentScanVerdict.ERROR
    assert called is False


def test_ping_success_and_failure() -> None:
    ok = _FakeSocket([b"PONG"])
    scanner = _scanner(ok)
    assert scanner.ping() is True
    assert ok.sent.startswith(PING_COMMAND)

    def _down() -> socket.socket:
        raise OSError("down")

    assert ClamAVAttachmentScanner("x", 3310, 1.0, socket_factory=_down).ping() is False


def test_scan_result_has_no_filename_or_bytes() -> None:
    assert "filename" not in AttachmentScanResult.model_fields
    assert "content" not in AttachmentScanResult.model_fields
