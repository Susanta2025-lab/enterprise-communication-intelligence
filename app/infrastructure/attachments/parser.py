"""Dispatcher that routes CLEAN attachment bytes to a kind-specific parser."""

from app.domain.attachment_policy import detect_attachment_kind
from app.domain.enums import AttachmentKind
from app.domain.exceptions import AttachmentParseError, AttachmentUnsupportedError
from app.domain.interfaces.attachment_parser import AttachmentParser
from app.domain.models.attachment import AttachmentContent, ParsedAttachment
from app.infrastructure.attachments.docx import parse_docx_attachment
from app.infrastructure.attachments.image import parse_image_attachment
from app.infrastructure.attachments.pdf import parse_pdf_attachment
from app.infrastructure.attachments.txt import parse_txt_attachment


class SafeAttachmentParser(AttachmentParser):
    """Parse one already-validated attachment. Does not scan or invoke AI."""

    def parse(self, content: AttachmentContent, kind: AttachmentKind) -> ParsedAttachment:
        """Route by kind after confirming bytes still match the allowlist."""
        detected = detect_attachment_kind(content.content)
        if detected is None or detected is not kind:
            raise AttachmentUnsupportedError()
        if kind is AttachmentKind.PDF:
            return parse_pdf_attachment(content)
        if kind is AttachmentKind.DOCX:
            return parse_docx_attachment(content)
        if kind is AttachmentKind.TXT:
            return parse_txt_attachment(content)
        if kind in {AttachmentKind.JPEG, AttachmentKind.PNG}:
            return parse_image_attachment(content, kind)
        raise AttachmentParseError()
