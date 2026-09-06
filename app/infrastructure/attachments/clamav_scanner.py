"""ClamAV clamd client adapter. Binaries stay out of the ECI API image.

Communicates with a separate clamd service over the INSTREAM protocol.
Raw attachment bytes are streamed from memory and are never written to disk.
"""

from __future__ import annotations

import socket
from collections.abc import Callable

from app.domain.enums import AttachmentScanVerdict
from app.domain.interfaces.attachment_scanner import AttachmentScanner, AttachmentScanResult
from app.domain.models.attachment import AttachmentContent
from app.infrastructure.attachments.clamav_protocol import (
    INSTREAM_COMMAND,
    MAX_RESPONSE_BYTES,
    MAX_SCAN_BYTES,
    PING_COMMAND,
    instream_frames,
    is_pong,
    map_clamd_response,
)

SocketFactory = Callable[[], socket.socket]


class ClamAVAttachmentScanner(AttachmentScanner):
    """Scan one already-retrieved attachment through an external clamd."""

    def __init__(
        self,
        host: str,
        port: int,
        timeout_seconds: float,
        *,
        socket_factory: SocketFactory | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._timeout_seconds = timeout_seconds
        self._socket_factory = socket_factory

    def scan(self, content: AttachmentContent) -> AttachmentScanResult:
        """Stream one attachment to clamd. Failures never become CLEAN."""
        payload = content.content
        if len(payload) > MAX_SCAN_BYTES:
            return AttachmentScanResult(verdict=AttachmentScanVerdict.ERROR)
        try:
            frames = instream_frames(payload)
            raw = self._exchange(INSTREAM_COMMAND, frames)
        except OSError:
            return AttachmentScanResult(verdict=AttachmentScanVerdict.ERROR)
        except ValueError:
            return AttachmentScanResult(verdict=AttachmentScanVerdict.ERROR)
        except Exception:
            return AttachmentScanResult(verdict=AttachmentScanVerdict.ERROR)
        return AttachmentScanResult(verdict=map_clamd_response(raw))

    def ping(self) -> bool:
        """Bounded liveness check. Does not expose the scanner address."""
        try:
            raw = self._exchange(PING_COMMAND, ())
        except OSError:
            return False
        except Exception:
            return False
        return is_pong(raw)

    def _exchange(self, command: bytes, frames: tuple[bytes, ...] | list[bytes]) -> bytes:
        sock = self._open()
        try:
            sock.settimeout(self._timeout_seconds)
            sock.sendall(command)
            for frame in frames:
                sock.sendall(frame)
            return _recv_bounded(sock, MAX_RESPONSE_BYTES)
        finally:
            _close(sock)

    def _open(self) -> socket.socket:
        if self._socket_factory is not None:
            return self._socket_factory()
        return socket.create_connection((self._host, self._port), self._timeout_seconds)


def _recv_bounded(sock: socket.socket, limit: int) -> bytes:
    chunks: list[bytes] = []
    received = 0
    while received < limit:
        piece = sock.recv(min(256, limit - received))
        if not piece:
            break
        chunks.append(piece)
        received += len(piece)
        if piece.endswith(b"\0") or piece.endswith(b"\n"):
            break
    return b"".join(chunks)[:limit]


def _close(sock: socket.socket) -> None:
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    sock.close()
