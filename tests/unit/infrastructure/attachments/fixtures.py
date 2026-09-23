"""Synthetic attachment fixtures. No real documents or malware samples."""

from __future__ import annotations

import io
import struct
import zipfile
import zlib

from docx import Document
from PIL import Image
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.domain.enums import AttachmentDisposition
from app.domain.models import AttachmentContent, AttachmentMetadata


def attachment_content(
    payload: bytes,
    *,
    filename: str,
    media_type: str,
    attachment_id: str = "att-1",
    message_id: str = "fake-msg-001",
) -> AttachmentContent:
    return AttachmentContent(
        metadata=AttachmentMetadata(
            provider_attachment_id=attachment_id,
            filename=filename,
            media_type=media_type,
            reported_size=len(payload),
            disposition=AttachmentDisposition.ATTACHMENT,
        ),
        content=payload,
        source_message_id=message_id,
        source_attachment_id=attachment_id,
    )


def pdf_with_text(*page_texts: str) -> bytes:
    writer = PdfWriter()
    for text in page_texts:
        page = writer.add_blank_page(width=300, height=300)
        font = writer._add_object(
            DictionaryObject(
                {
                    NameObject("/Type"): NameObject("/Font"),
                    NameObject("/Subtype"): NameObject("/Type1"),
                    NameObject("/BaseFont"): NameObject("/Helvetica"),
                }
            )
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
        )
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        content = DecodedStreamObject()
        content.set_data(f"BT /F1 12 Tf 36 250 Td ({escaped}) Tj ET".encode("latin-1", "replace"))
        page[NameObject("/Contents")] = writer._add_object(content)
    return _write_pdf(writer)


def pdf_blank_pages(count: int) -> bytes:
    writer = PdfWriter()
    for _ in range(count):
        writer.add_blank_page(width=200, height=200)
    return _write_pdf(writer)


def pdf_encrypted() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.encrypt("secret")
    return _write_pdf(writer)


def pdf_with_ignored_actions(text: str = "Visible contract text") -> bytes:
    payload = pdf_with_text(text)
    header_end = payload.find(b"\n")
    comment = b"% /JS (app.alert('x')) /JavaScript /Launch /EmbeddedFile /URI\n"
    if header_end == -1:
        return comment + payload
    return payload[: header_end + 1] + comment + payload[header_end + 1 :]


def docx_with_text(*paragraphs: str, tables: list[list[list[str]]] | None = None) -> bytes:
    document = Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    for table_data in tables or []:
        table = document.add_table(rows=len(table_data), cols=len(table_data[0]))
        for row_index, row in enumerate(table_data):
            for col_index, value in enumerate(row):
                table.rows[row_index].cells[col_index].text = value
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def docx_with_zip_member(name: str, member_bytes: bytes = b"ignored") -> bytes:
    payload = bytearray(docx_with_text("Visible paragraph"))
    buffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(payload), "r") as source:
        with zipfile.ZipFile(buffer, "w") as dest:
            for info in source.infolist():
                dest.writestr(info, source.read(info.filename))
            dest.writestr(name, member_bytes)
    return buffer.getvalue()


def docx_with_external_relationship() -> bytes:
    payload = docx_with_text("Contract body")
    buffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(payload), "r") as source:
        with zipfile.ZipFile(buffer, "w") as dest:
            for info in source.infolist():
                data = source.read(info.filename)
                if info.filename.endswith("document.xml.rels"):
                    external = (
                        b'<Relationship Id="rEvil" '
                        b'Type="http://schemas.openxmlformats.org/officeDocument/'
                        b'2006/relationships/hyperlink" '
                        b'Target="https://evil.example/ignore" '
                        b'TargetMode="External"/>'
                    )
                    data = data.replace(b"</Relationships>", external + b"</Relationships>")
                dest.writestr(info, data)
    return buffer.getvalue()


def minimal_xlsx_bytes(
    *,
    extra: dict[str, bytes] | None = None,
    include_vba: bool = False,
    include_workbook_rels: bool = True,
) -> bytes:
    """Synthetic OOXML spreadsheet container. No real business data."""
    buffer = io.BytesIO()
    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Types "
        'xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" '
        'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.'
        'spreadsheetml.sheet.main+xml"/>'
        "</Types>"
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<workbook "
        'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/'
        'relationships"/>'
        "</sheets></workbook>"
    )
    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Relationships "
        'xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/'
        'relationships/officeDocument" '
        'Target="worksheets/sheet1.xml"/>'
        "</Relationships>"
    )
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("xl/workbook.xml", workbook)
        if include_workbook_rels:
            archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        if include_vba:
            archive.writestr("xl/vbaProject.bin", b"macro")
        for name, data in (extra or {}).items():
            archive.writestr(name, data)
    return buffer.getvalue()


def xlsx_with_external_relationship() -> bytes:
    external_rels = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b"<Relationships "
        b'xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        b'<Relationship Id="rId1" '
        b'Type="http://schemas.openxmlformats.org/officeDocument/2006/'
        b'relationships/officeDocument" '
        b'Target="worksheets/sheet1.xml"/>'
        b'<Relationship Id="rEvil" '
        b'Type="http://schemas.openxmlformats.org/officeDocument/2006/'
        b'relationships/hyperlink" '
        b'Target="https://evil.example/ignore" '
        b'TargetMode="External"/>'
        b"</Relationships>"
    )
    return minimal_xlsx_bytes(
        extra={"xl/_rels/workbook.xml.rels": external_rels},
        include_workbook_rels=False,
    )


def xlsx_with_formula_cells() -> bytes:
    """Minimal workbook containing a formula cell via openpyxl (never executed)."""
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet["A1"] = 1
    sheet["A2"] = 2
    sheet["A3"] = "=A1+A2"
    sheet["B1"] = '=HYPERLINK("https://evil.example","x")'
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def xlsx_workbook(
    sheets: list[dict] | None = None,
) -> bytes:
    """Build a synthetic XLSX workbook with optional multi-sheet layout.

    Each sheet dict may include:
    - name: str
    - state: visible|hidden|veryHidden
    - rows: list[list[object]] (cell values; formulas as strings starting with =)
    """
    from openpyxl import Workbook

    workbook = Workbook()
    # Remove the default sheet after creating the first requested sheet.
    default = workbook.active
    sheet_specs = sheets or [{"name": "Sheet1", "rows": [["A", "B"], [1, 2]]}]
    first = True
    for spec in sheet_specs:
        name = spec.get("name", "Sheet1")
        if first:
            worksheet = default
            worksheet.title = name
            first = False
        else:
            worksheet = workbook.create_sheet(name)
        state = spec.get("state", "visible")
        worksheet.sheet_state = state
        for row_index, row in enumerate(spec.get("rows", []), start=1):
            for col_index, value in enumerate(row, start=1):
                worksheet.cell(row=row_index, column=col_index, value=value)
        merges = spec.get("merges", [])
        for merge in merges:
            worksheet.merge_cells(merge)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def tiny_jpeg() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (16, 16), color=(12, 34, 56)).save(buffer, format="JPEG")
    return buffer.getvalue()


def tiny_png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (16, 16), color=(9, 8, 7)).save(buffer, format="PNG")
    return buffer.getvalue()


def jpeg_with_exif_secret(secret: bytes = b"ECI-EXIF-GPS-SECRET") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (16, 16), color=(1, 2, 3)).save(buffer, format="JPEG")
    data = buffer.getvalue()
    app1 = b"\xff\xe1" + struct.pack(">H", len(secret) + 8) + b"Exif\x00\x00" + secret
    return data[:2] + app1 + data[2:]


def png_with_dimensions(width: int, height: int) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    idat = zlib.compress(b"\x00\x00\x00\x00")
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


def _write_pdf(writer: PdfWriter) -> bytes:
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()
