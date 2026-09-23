"""Provider-neutral attachment type, size, and signature policy.

Extension alone is never sufficient. Product Analyze allowlists PDF, DOCX,
JPEG, PNG, TXT, and XLSX (Phase 21D). XLSX uses bounded container validation,
extraction, and tabular AI after the CLEAN scan gate. Archives, executables, scripts, macro-enabled
Office, encrypted documents, legacy spreadsheet formats, and unknown binaries
fail closed.
"""

from __future__ import annotations

import io
import zipfile
import zlib
from collections.abc import Iterator
from dataclasses import dataclass
from xml.etree.ElementTree import ParseError

from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import iterparse

from app.domain.enums import AttachmentKind
from app.domain.exceptions import (
    AttachmentContentInvalidError,
    AttachmentExceedsLimitError,
    AttachmentUnsupportedError,
)
from app.domain.models import AttachmentContent, AttachmentMetadata

MAX_ATTACHMENT_CONTENT_BYTES = 5 * 1024 * 1024
MAX_PROCESSED_ATTACHMENT_CONTENT_BYTES = 10 * 1024 * 1024
MAX_PDF_PAGES = 50
MAX_EXTRACTED_TEXT_CHARS = 200_000
MAX_IMAGE_PIXELS = 20_000_000
MAX_IMAGE_DIMENSION = 8_000
MAX_IMAGE_UNCOMPRESSED_BYTES = 60 * 1024 * 1024
_DOCX_MAX_ENTRIES = 256
_DOCX_MAX_UNCOMPRESSED_TOTAL = 20 * 1024 * 1024
_DOCX_MAX_SINGLE_PART = 8 * 1024 * 1024
# Phase 21 readiness assessment §9 (XLSX ZIP envelope).
XLSX_MAX_ZIP_ENTRIES = 512
XLSX_MAX_UNCOMPRESSED_TOTAL = 20 * 1024 * 1024
XLSX_MAX_SINGLE_PART = 8 * 1024 * 1024
# Defense-in-depth ZIP-bomb ratio (not listed as a hard product KPI; fail closed).
XLSX_MAX_COMPRESSION_RATIO = 100

# Phase 21 readiness assessment §9 (bounded workbook extraction — Phase 21B).
XLSX_MAX_SHEETS = 10
XLSX_MAX_COLUMNS_PER_SHEET = 50
XLSX_MAX_DATA_ROWS_PER_SHEET = 100  # excluding inferred header row
XLSX_MAX_TOTAL_CELLS = 5_000
# Implementation safeguard subordinate to MAX_EXTRACTED_TEXT_CHARS (not §9-locked).
XLSX_MAX_CELL_CHARS = 2_000
# Phase 21C: hard AI-input cap (readiness §9 preferred ~32–64 KiB; lock smallest).
# Character-based, UTF-8-safe (Python str slicing), same for Mock/Foundry/Bedrock.
# Must remain strictly below MAX_EXTRACTED_TEXT_CHARS.
XLSX_AI_INPUT_MAX_CHARS = 32_768
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

_XLSX_CONTENT_TYPES = "[Content_Types].xml"
_XLSX_WORKBOOK = "xl/workbook.xml"
_XLSX_VBA = "xl/vbaProject.bin"
_XLSX_CONNECTIONS = "xl/connections.xml"
_XLSX_EXTERNAL_LINKS_PREFIX = "xl/externalLinks/"
_XLSX_EMBEDDINGS_PREFIX = "xl/embeddings/"
_XLSX_ENCRYPTION_MARKERS = frozenset({"encryptioninfo", "encryptedpackage"})
_XLSX_MACRO_CONTENT_MARKERS = (
    "macroenabled",
    "vbaproject",
)

# openpyxl must never evaluate formulas. Phase 21B must load with these settings.
OPENPYXL_READ_ONLY = True
OPENPYXL_DATA_ONLY = False
OPENPYXL_KEEP_VBA = False

_KIND_EXTENSIONS: dict[AttachmentKind, frozenset[str]] = {
    AttachmentKind.PDF: frozenset({".pdf"}),
    AttachmentKind.DOCX: frozenset({".docx"}),
    AttachmentKind.JPEG: frozenset({".jpg", ".jpeg"}),
    AttachmentKind.PNG: frozenset({".png"}),
    AttachmentKind.TXT: frozenset({".txt"}),
    AttachmentKind.XLSX: frozenset({".xlsx"}),
}

_KIND_MEDIA_TYPES: dict[AttachmentKind, frozenset[str]] = {
    AttachmentKind.PDF: frozenset({"application/pdf"}),
    AttachmentKind.DOCX: frozenset(
        {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
    ),
    AttachmentKind.JPEG: frozenset({"image/jpeg"}),
    AttachmentKind.PNG: frozenset({"image/png"}),
    AttachmentKind.TXT: frozenset({"text/plain"}),
    AttachmentKind.XLSX: frozenset(
        {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
    ),
}

# Product Analyze path (pre-retrieval). Authoritative allowlist for Analyze.
_PRODUCT_ANALYSIS_KINDS = frozenset(
    {
        AttachmentKind.PDF,
        AttachmentKind.DOCX,
        AttachmentKind.JPEG,
        AttachmentKind.PNG,
        AttachmentKind.TXT,
        AttachmentKind.XLSX,
    }
)

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
        ".xlsb",
        ".xls",
        ".csv",
        ".tsv",
        ".pptm",
        ".ppt",
    }
)


@dataclass(frozen=True, slots=True)
class XlsxContainerValidationResult:
    """Bounded metadata from a successful XLSX container security check.

    Never contains cell values, formulas, sheet names, or member payloads.
    """

    recognized: bool
    compressed_size: int
    aggregate_uncompressed_size: int
    archive_member_count: int
    warnings: tuple[str, ...]


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


def xlsx_product_analysis_enabled() -> bool:
    """Return whether product Analyze accepts ``xlsx``.

    Phase 21D enables XLSX once the attachment_analyses kind constraint and
    tabular Analyze path are available. Keep this aligned with
    ``_PRODUCT_ANALYSIS_KINDS`` — do not diverge allowlists.
    """
    return AttachmentKind.XLSX in _PRODUCT_ANALYSIS_KINDS


def evaluate_attachment_metadata(metadata: AttachmentMetadata) -> AttachmentKind:
    """Fail-closed metadata pre-check. Does not retrieve or inspect bytes."""
    if metadata.reported_size == 0:
        raise AttachmentUnsupportedError()
    if metadata.reported_size > MAX_ATTACHMENT_CONTENT_BYTES:
        raise AttachmentExceedsLimitError()
    kind = _declared_kind(metadata)
    if kind not in _PRODUCT_ANALYSIS_KINDS:
        raise AttachmentUnsupportedError()
    return kind


def validate_attachment_content_size(content: AttachmentContent) -> None:
    """Bound bytes before scanning without inspecting a workbook container."""
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


def evaluate_attachment_content(content: AttachmentContent) -> AttachmentKind:
    """Validate retrieved bytes against size, type, and signature policy."""
    validate_attachment_content_size(content)
    declared = _declared_kind(content.metadata)
    detected = detect_attachment_kind(content.content)
    if detected is None:
        raise AttachmentUnsupportedError()
    if detected != declared:
        raise AttachmentUnsupportedError()
    if declared is AttachmentKind.DOCX:
        _validate_docx_container(content.content)
    if declared is AttachmentKind.XLSX:
        validate_xlsx_container(content.content)
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
        if _looks_like_xlsx_names(payload):
            matches.append(AttachmentKind.XLSX)
    if _looks_like_txt(payload) and not matches:
        matches.append(AttachmentKind.TXT)
    if len(matches) != 1:
        return None
    return matches[0]


def validate_xlsx_container(payload: bytes) -> XlsxContainerValidationResult:
    """Inspect an XLSX OOXML ZIP without workbook parsing or formula execution.

    Rejects macros, encryption, external relationships/links, path traversal,
    and ZIP resource abuse. Embedded OLE packages are recorded as warnings and
    ignored (never opened). Does not write members to disk.
    """
    if _has_hostile_binary_signature(payload):
        raise AttachmentUnsupportedError()
    if not (payload.startswith(_ZIP_LOCAL) or payload.startswith(_ZIP_EMPTY)):
        raise AttachmentUnsupportedError()
    names, member_count, uncompressed_total = _zip_member_inventory(
        payload,
        max_entries=XLSX_MAX_ZIP_ENTRIES,
        max_single_part=XLSX_MAX_SINGLE_PART,
        max_uncompressed_total=XLSX_MAX_UNCOMPRESSED_TOTAL,
        max_compression_ratio=XLSX_MAX_COMPRESSION_RATIO,
        strict_xlsx=True,
    )
    if _XLSX_VBA in names:
        raise AttachmentUnsupportedError()
    if any(name.split("/")[-1].lower() in _XLSX_ENCRYPTION_MARKERS for name in names):
        raise AttachmentUnsupportedError()
    if _XLSX_CONTENT_TYPES not in names or _XLSX_WORKBOOK not in names:
        raise AttachmentUnsupportedError()
    if _DOCX_DOCUMENT in names:
        raise AttachmentUnsupportedError()
    if any(name.startswith(_XLSX_EXTERNAL_LINKS_PREFIX) for name in names):
        raise AttachmentUnsupportedError()
    if _XLSX_CONNECTIONS in names:
        raise AttachmentUnsupportedError()
    _reject_xlsx_macro_content_types(payload, names)
    if _xlsx_has_external_relationship(payload, names):
        raise AttachmentUnsupportedError()

    warnings: list[str] = []
    if any(name.startswith(_XLSX_EMBEDDINGS_PREFIX) for name in names):
        warnings.append("xlsx_embedded_object_ignored")

    return XlsxContainerValidationResult(
        recognized=True,
        compressed_size=len(payload),
        aggregate_uncompressed_size=uncompressed_total,
        archive_member_count=member_count,
        warnings=tuple(warnings),
    )


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


def decode_txt_attachment(payload: bytes) -> str:
    """Decode an already-validated TXT payload. Reject undecodable bytes."""
    decoded = _decode_text_bytes(payload)
    if decoded is None:
        raise AttachmentContentInvalidError()
    if decoded.startswith("\ufeff"):
        decoded = decoded[1:]
    return decoded


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
        names, _, _ = _zip_member_inventory(
            payload,
            max_entries=_DOCX_MAX_ENTRIES,
            max_single_part=_DOCX_MAX_SINGLE_PART,
            max_uncompressed_total=_DOCX_MAX_UNCOMPRESSED_TOTAL,
            max_compression_ratio=None,
        )
    except AttachmentUnsupportedError:
        return False
    except AttachmentExceedsLimitError:
        return False
    return (
        _DOCX_CONTENT_TYPES in names
        and _DOCX_DOCUMENT in names
        and _XLSX_WORKBOOK not in names
    )


def _looks_like_xlsx_names(payload: bytes) -> bool:
    try:
        names, _, _ = _zip_member_inventory(
            payload,
            max_entries=XLSX_MAX_ZIP_ENTRIES,
            max_single_part=XLSX_MAX_SINGLE_PART,
            max_uncompressed_total=XLSX_MAX_UNCOMPRESSED_TOTAL,
            max_compression_ratio=XLSX_MAX_COMPRESSION_RATIO,
            strict_xlsx=True,
        )
    except AttachmentUnsupportedError:
        return False
    except AttachmentExceedsLimitError:
        return False
    return (
        _XLSX_CONTENT_TYPES in names
        and _XLSX_WORKBOOK in names
        and _DOCX_DOCUMENT not in names
    )


def _validate_docx_container(payload: bytes) -> None:
    if _has_hostile_binary_signature(payload):
        raise AttachmentUnsupportedError()
    if not (payload.startswith(_ZIP_LOCAL) or payload.startswith(_ZIP_EMPTY)):
        raise AttachmentUnsupportedError()
    names, _, _ = _zip_member_inventory(
        payload,
        max_entries=_DOCX_MAX_ENTRIES,
        max_single_part=_DOCX_MAX_SINGLE_PART,
        max_uncompressed_total=_DOCX_MAX_UNCOMPRESSED_TOTAL,
        max_compression_ratio=None,
    )
    if _DOCX_VBA in names:
        raise AttachmentUnsupportedError()
    if any(name.split("/")[-1].lower() in _DOCX_ENCRYPTION_MARKERS for name in names):
        raise AttachmentUnsupportedError()
    if _DOCX_CONTENT_TYPES not in names or _DOCX_DOCUMENT not in names:
        raise AttachmentUnsupportedError()


def _xlsx_xml_attributes(payload: bytes, name: str) -> Iterator[dict[str, str]]:
    """Stream security metadata with DTD/entity expansion disabled.

    ZIP bounds have already been checked. Normalize corrupt-member/XML errors
    without retaining member contents in the public exception.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive, archive.open(name) as part:
            for _, element in iterparse(part, events=("end",), forbid_dtd=True):
                yield element.attrib
                element.clear()
    except (
        zipfile.BadZipFile, KeyError, OSError, RuntimeError, NotImplementedError,
        ValueError, ParseError, DefusedXmlException, EOFError, zlib.error,
    ):
        raise AttachmentUnsupportedError() from None


def _reject_xlsx_macro_content_types(payload: bytes, names: set[str]) -> None:
    for attributes in _xlsx_xml_attributes(payload, _XLSX_CONTENT_TYPES):
        content_type = attributes.get("ContentType", "").lower()
        if any(marker in content_type for marker in _XLSX_MACRO_CONTENT_MARKERS):
            raise AttachmentUnsupportedError()


def _xlsx_has_external_relationship(payload: bytes, names: set[str]) -> bool:
    for name in sorted(names):
        if not name.lower().endswith(".rels"):
            continue
        for attributes in _xlsx_xml_attributes(payload, name):
            if attributes.get("TargetMode", "").strip().lower() == "external":
                return True
    return False


def _zip_member_inventory(
    payload: bytes,
    *,
    max_entries: int,
    max_single_part: int,
    max_uncompressed_total: int,
    max_compression_ratio: int | None,
    strict_xlsx: bool = False,
) -> tuple[set[str], int, int]:
    """Return member names, count, and aggregate uncompressed size from ZIP metadata.

    Inspects central-directory claims only. Does not extract members to disk.
    """
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile:
        raise AttachmentUnsupportedError() from None
    with archive:
        infos = archive.infolist()
        if len(infos) > max_entries:
            raise AttachmentUnsupportedError()
        total_uncompressed = 0
        names: set[str] = set()
        for info in infos:
            name = info.filename.replace("\\", "/")
            if strict_xlsx and (
                info.flag_bits & 1
                or name in names
                or "\\" in info.filename
                or ":" in name
                or "." in name.split("/")
                or info.orig_filename != info.filename
                or info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
            ):
                raise AttachmentUnsupportedError()
            if name.startswith("/") or ".." in name.split("/"):
                raise AttachmentUnsupportedError()
            if info.file_size > max_single_part:
                raise AttachmentExceedsLimitError()
            if (
                max_compression_ratio is not None
                and info.compress_size > 0
                and info.file_size > info.compress_size * max_compression_ratio
            ):
                raise AttachmentUnsupportedError()
            total_uncompressed += info.file_size
            if total_uncompressed > max_uncompressed_total:
                raise AttachmentExceedsLimitError()
            names.add(name)
        return names, len(infos), total_uncompressed
