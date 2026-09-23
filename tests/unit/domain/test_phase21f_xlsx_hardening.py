"""Semantic OOXML and malformed-container regression tests; synthetic data only."""

import io
import struct
import zipfile

import pytest

from app.domain.attachment_policy import validate_xlsx_container
from app.domain.exceptions import AttachmentUnsupportedError
from tests.unit.infrastructure.attachments.fixtures import minimal_xlsx_bytes


def _replace_part(payload, name, data):
    target = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(payload)) as source, zipfile.ZipFile(target, "w") as dest:
        for info in source.infolist():
            dest.writestr(info.filename, data if info.filename == name else source.read(info))
    return target.getvalue()


@pytest.mark.parametrize("attribute", ['TargetMode = "External"', 'TargetMode="Exter&#110;al"'])
@pytest.mark.parametrize("encoding", ["utf-8", "utf-16"])
def test_semantically_external_relationship_is_rejected(attribute, encoding):
    xml = (
        f'<?xml version="1.0" encoding="{encoding}"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f'<Relationship Id="r1" Target="https://example.invalid" {attribute}/>'
        '</Relationships>'
    ).encode(encoding)
    payload = _replace_part(minimal_xlsx_bytes(), "xl/_rels/workbook.xml.rels", xml)
    with pytest.raises(AttachmentUnsupportedError):
        validate_xlsx_container(payload)


@pytest.mark.parametrize("encoding", ["utf-8", "utf-16"])
def test_encoded_macro_content_type_is_rejected(encoding):
    xml = (
        f'<?xml version="1.0" encoding="{encoding}"?>'
        '<Types><Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.ms-excel.sheet.macro&#69;nabled.main+xml"/></Types>'
    ).encode(encoding)
    payload = _replace_part(minimal_xlsx_bytes(), "[Content_Types].xml", xml)
    with pytest.raises(AttachmentUnsupportedError):
        validate_xlsx_container(payload)


@pytest.mark.parametrize("xml", [b'<Relationships', b'<!DOCTYPE r [<!ENTITY a "x">]><r>&a;</r>'])
def test_invalid_or_entity_xml_is_rejected(xml):
    payload = _replace_part(minimal_xlsx_bytes(), "xl/_rels/workbook.xml.rels", xml)
    with pytest.raises(AttachmentUnsupportedError):
        validate_xlsx_container(payload)


def test_corrupt_member_crc_is_normalized():
    payload = bytearray(_replace_part(minimal_xlsx_bytes(), "[Content_Types].xml", b'<Types/>'))
    offset = payload.index(b'<Types/>')
    payload[offset + 1] = ord('X')
    with pytest.raises(AttachmentUnsupportedError):
        validate_xlsx_container(bytes(payload))


def test_encrypted_zip_flag_is_rejected_before_member_read():
    payload = bytearray(minimal_xlsx_bytes())
    offset = payload.index(b'PK\x01\x02')
    struct.pack_into('<H', payload, offset + 8, 1)
    with pytest.raises(AttachmentUnsupportedError):
        validate_xlsx_container(bytes(payload))


def test_duplicate_zip_member_is_rejected():
    target = io.BytesIO(minimal_xlsx_bytes())
    with zipfile.ZipFile(target, 'a') as archive, pytest.warns(UserWarning):
        archive.writestr('xl/workbook.xml', '<workbook/>')
    with pytest.raises(AttachmentUnsupportedError):
        validate_xlsx_container(target.getvalue())


@pytest.mark.parametrize('name', ['C:/evil.xml', 'xl\\evil.xml', 'xl/./evil.xml'])
def test_ambiguous_member_paths_are_rejected(name):
    with pytest.raises(AttachmentUnsupportedError):
        validate_xlsx_container(minimal_xlsx_bytes(extra={name: b'x'}))
