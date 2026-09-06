"""Provider-neutral attachment type, size, and signature policy.

Extension alone is never sufficient. Allowed Phase 18 kinds are PDF, DOCX,
JPEG, PNG, and TXT. Archives, executables, scripts, macro-enabled Office,
encrypted documents, and unknown binaries fail closed.
"""

from __future__ import annotations

import io
import zipfile

from app.domain.enums import AttachmentKind
from app.domain.exceptions import (
    AttachmentContentInvalidError,
    AttachmentExceedsLimitError,
    AttachmentUnsupportedError,
)
from app.domain.models import AttachmentContent, AttachmentMetadata

MAX_ATTACHMENT_CONTENT_BYTES = 5 * 1024 * 1024
MAX_PROCESSED_ATTACHMENT_CONTENT_BYTES = 10 * 1024 * 1024
_DOCX_MAX_ENTRIES = 256
_DOCX_MAX_UNCOMPRESSED_TOTAL = 20 * 1024 * 1024
_DOCX_MAX_SINGLE_PART = 8 * 1024 * 1024
_PDF_PREFIX_WINDOW = 8192
_TXT_CONTROL_ALLOWLIST = frozenset({9, 10, 13})

_PDF_SIGNATURE = b"%PDF-"
_JPEG_SOI = b"\xff\xd8\xff"
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_ZIP_LOCAL = b"PK\x03\x04"
_ZIP_EMPTY = b"PK\x05\x06"
_OLE_SIGNATURE = b"\xd0\xcf\x11\xe0"
_MZ_SIGNATURE = b"MZ"
_ELF_SIGNATURE = b"\x7fELF"
_RAR_SIGNATURE = b"Rar!"
_SEVEN_Z_SIGNATURE = b"7z\xbc\xaf'\x1c"
_GZIP_SIGNATURE = b"\x1f\x8b"

_DOCX_CONTENT_TYPES = "[Content_Types].xml"
_DOCX_DOCUMENT = "word/document.xml"
_DOCX_VBA = "word/vbaProject.bin"
_DOCX_ENCRYPTION_MARKERS = frozenset({"encryptioninfo", "encryptedpackage"})

_KIND_EXTENSIONS: dict[AttachmentKind, frozenset[str]] = {
    AttachmentKind.PDF: frozenset({".pdf"}),
    AttachmentKind.DOCX: frozenset({".docx"}),
    AttachmentKind.JPEG: frozenset({".jpg", ".jpeg"}),
    AttachmentKind.PNG: frozenset({".png"}),
    AttachmentKind.TXT: frozenset({".txt"}),
}

_KIND_MEDIA_TYPES: dict[AttachmentKind, frozenset[str]] = {
    AttachmentKind.PDF: frozenset({"application/pdf"}),
    AttachmentKind.DOCX: frozenset(
        {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
    ),
    AttachmentKind.JPEG: frozenset({"image/jpeg"}),
    AttachmentKind.PNG: frozenset({"image/png"}),
    AttachmentKind.TXT: frozenset({"text/plain"}),
}

_REJECTED_EXTENSIONS = frozenset(
    {
        ".zip",
        ".rar",
        ".7z",
        ".tar",
        ".gz",
        ".tgz",
        ".bz2",
        ".xz",
        ".exe",
        ".dll",
        ".bat",
        ".cmd",
        ".ps1",
        ".sh",
        ".js",
        ".vbs",
        ".wsf",
        ".html",
        ".htm",
        ".svg",
        ".xml",
        ".doc",
        ".docm",
        ".dotm",
        ".xlsm",
        ".pptm",
        ".xls",
        ".ppt",
    }
)


class AttachmentContentBudget:
    """In-memory processed-content budget for one message or request session.

    Not persisted. Later API/service work can hold one instance per request
    without changing this type.
    """

    def __init__(
        self,
        *,
        limit_bytes: int = MAX_PROCESSED_ATTACHMENT_CONTENT_BYTES,
        consumed_bytes: int = 0,
    ) -> None:
        self.limit_bytes = limit_bytes
        self.consumed_bytes = consumed_bytes

    def remaining_bytes(self) -> int:
        """Return unused budget. Never negative."""
        return max(self.limit_bytes - self.consumed_bytes, 0)

    def consume(self, size: int) -> None:
        """Consume ``size`` decoded bytes or fail closed if the budget is exceeded."""
        if size < 0:
            raise AttachmentContentInvalidError()
        if self.consumed_bytes + size > self.limit_bytes:
            raise AttachmentExceedsLimitError()
        self.consumed_bytes += size


def evaluate_attachment_metadata(metadata: AttachmentMetadata) -> AttachmentKind:
    """Fail-closed metadata pre-check. Does not retrieve or inspect bytes."""
    if metadata.reported_size == 0:
        raise AttachmentUnsupportedError()
    if metadata.reported_size > MAX_ATTACHMENT_CONTENT_BYTES:
        raise AttachmentExceedsLimitError()
    return _declared_kind(metadata)


def evaluate_attachment_content(content: AttachmentContent) -> AttachmentKind:
    """Validate retrieved bytes against size, type, and signature policy."""
    actual = len(content.content)
    reported = content.metadata.reported_size
    if actual == 0:
        raise AttachmentUnsupportedError()
    if actual > MAX_ATTACHMENT_CONTENT_BYTES:
        raise AttachmentExceedsLimitError()
    if reported > MAX_ATTACHMENT_CONTENT_BYTES:
        raise AttachmentExceedsLimitError()
    if actual > reported:
        raise AttachmentContentInvalidError()
    declared = _declared_kind(content.metadata)
    detected = detect_attachment_kind(content.content)
    if detected is None:
        raise AttachmentUnsupportedError()
    if detected != declared:
        raise AttachmentUnsupportedError()
    if declared is AttachmentKind.DOCX:
        _validate_docx_container(content.content)
    if declared is AttachmentKind.TXT:
        _validate_txt_payload(content.content)
    if declared is AttachmentKind.PDF:
        _validate_pdf_prefix(content.content)
    if declared is AttachmentKind.JPEG:
        _validate_jpeg_payload(content.content)
    return declared


def detect_attachment_kind(payload: bytes) -> AttachmentKind | None:
    """Return the unique allowlisted kind for ``payload``, or None.

    Polyglot payloads that match more than one allowed magic fail closed.
    """
    if not payload:
        return None
    matches: list[AttachmentKind] = []
    if payload.startswith(_PDF_SIGNATURE):
        matches.append(AttachmentKind.PDF)
    if payload.startswith(_JPEG_SOI):
        matches.append(AttachmentKind.JPEG)
    if payload.startswith(_PNG_SIGNATURE):
        matches.append(AttachmentKind.PNG)
    if payload.startswith(_ZIP_LOCAL) or payload.startswith(_ZIP_EMPTY):
        if _looks_like_docx_names(payload):
            matches.append(AttachmentKind.DOCX)
    if _looks_like_txt(payload) and not matches:
        matches.append(AttachmentKind.TXT)
    if len(matches) != 1:
        return None
    return matches[0]


def attachment_size_bucket(size: int) -> str:
    """Return a coarse size label safe for structured logs."""
    if size <= 0:
        return "empty"
    if size <= 64 * 1024:
        return "le_64kib"
    if size <= 512 * 1024:
        return "le_512kib"
    if size <= 1024 * 1024:
        return "le_1mib"
    if size <= MAX_ATTACHMENT_CONTENT_BYTES:
        return "le_5mib"
    return "gt_5mib"


def _declared_kind(metadata: AttachmentMetadata) -> AttachmentKind:
    extension = _filename_extension(metadata.filename)
    if extension in _REJECTED_EXTENSIONS:
        raise AttachmentUnsupportedError()
    extension_kind = _kind_for_extension(extension)
    media_kind = _kind_for_media_type(metadata.media_type)
    if extension_kind is None and media_kind is None:
        raise AttachmentUnsupportedError()
    if extension_kind is None or media_kind is None:
        raise AttachmentUnsupportedError()
    if extension_kind != media_kind:
        raise AttachmentUnsupportedError()
    return extension_kind


def _filename_extension(filename: str) -> str:
    trimmed = filename.strip()
    if not trimmed:
        return ""
    name = trimmed.replace("\\", "/").rsplit("/", 1)[-1]
    if name.startswith(".") and name.count(".") == 1:
        return ""
    if "." not in name:
        return ""
    return f".{name.rsplit('.', 1)[-1].lower()}"


def _kind_for_extension(extension: str) -> AttachmentKind | None:
    if not extension:
        return None
    for kind, extensions in _KIND_EXTENSIONS.items():
        if extension in extensions:
            return kind
    return None


def _kind_for_media_type(media_type: str) -> AttachmentKind | None:
    for kind, types in _KIND_MEDIA_TYPES.items():
        if media_type in types:
            return kind
    return None


def _validate_jpeg_payload(payload: bytes) -> None:
    if len(payload) < 4 or not payload.startswith(_JPEG_SOI):
        raise AttachmentUnsupportedError()
    marker = payload[3]
    if marker == 0x00:
        raise AttachmentUnsupportedError()


def _validate_pdf_prefix(payload: bytes) -> None:
    if not payload.startswith(_PDF_SIGNATURE):
        raise AttachmentUnsupportedError()
    window = payload[:_PDF_PREFIX_WINDOW]
    if b"/Encrypt" in window:
        raise AttachmentUnsupportedError()
    lowered = window.lower()
    if b"<html" in lowered or b"<script" in lowered or b"javascript:" in lowered:
        raise AttachmentUnsupportedError()


def _validate_txt_payload(payload: bytes) -> None:
    if not _looks_like_txt(payload):
        raise AttachmentUnsupportedError()


def _looks_like_txt(payload: bytes) -> bool:
    if not payload:
        return False
    if payload.startswith(_PDF_SIGNATURE):
        return False
    if payload.startswith(_JPEG_SOI) or payload.startswith(_PNG_SIGNATURE):
        return False
    if payload.startswith(_ZIP_LOCAL) or payload.startswith(_ZIP_EMPTY):
        return False
    if _has_hostile_binary_signature(payload):
        return False
    decoded = _decode_text_bytes(payload)
    if decoded is None:
        return False
    if "\x00" in decoded:
        return False
    return True


def _decode_text_bytes(payload: bytes) -> str | None:
    if payload.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return payload.decode("utf-16")
        except UnicodeDecodeError:
            return None
    if payload.startswith(b"\xef\xbb\xbf"):
        try:
            return payload.decode("utf-8-sig")
        except UnicodeDecodeError:
            return None
    if b"\x00" in payload:
        return None
    if any(byte < 32 and byte not in _TXT_CONTROL_ALLOWLIST for byte in payload):
        return None
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _has_hostile_binary_signature(payload: bytes) -> bool:
    return payload.startswith(
        (
            _OLE_SIGNATURE,
            _MZ_SIGNATURE,
            _ELF_SIGNATURE,
            _RAR_SIGNATURE,
            _SEVEN_Z_SIGNATURE,
            _GZIP_SIGNATURE,
        )
    )


def _looks_like_docx_names(payload: bytes) -> bool:
    try:
        names = _docx_member_names(payload)
    except AttachmentUnsupportedError:
        return False
    except AttachmentContentInvalidError:
        return False
    return _DOCX_CONTENT_TYPES in names and _DOCX_DOCUMENT in names


def _validate_docx_container(payload: bytes) -> None:
    if _has_hostile_binary_signature(payload):
        raise AttachmentUnsupportedError()
    if not (payload.startswith(_ZIP_LOCAL) or payload.startswith(_ZIP_EMPTY)):
        raise AttachmentUnsupportedError()
    names = _docx_member_names(payload)
    if _DOCX_VBA in names:
        raise AttachmentUnsupportedError()
    if any(name.split("/")[-1].lower() in _DOCX_ENCRYPTION_MARKERS for name in names):
        raise AttachmentUnsupportedError()
    if _DOCX_CONTENT_TYPES not in names or _DOCX_DOCUMENT not in names:
        raise AttachmentUnsupportedError()


def _docx_member_names(payload: bytes) -> set[str]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile:
        raise AttachmentUnsupportedError() from None
    with archive:
        infos = archive.infolist()
        if len(infos) > _DOCX_MAX_ENTRIES:
            raise AttachmentUnsupportedError()
        total_uncompressed = 0
        names: set[str] = set()
        for info in infos:
            name = info.filename.replace("\\", "/")
            if name.startswith("/") or ".." in name.split("/"):
                raise AttachmentUnsupportedError()
            if info.file_size > _DOCX_MAX_SINGLE_PART:
                raise AttachmentExceedsLimitError()
            total_uncompressed += info.file_size
            if total_uncompressed > _DOCX_MAX_UNCOMPRESSED_TOTAL:
                raise AttachmentExceedsLimitError()
            names.add(name)
        return names
