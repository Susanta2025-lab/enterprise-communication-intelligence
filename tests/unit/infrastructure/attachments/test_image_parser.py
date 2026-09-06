"""JPEG/PNG preparation tests. EXIF is not forwarded. OCR is not used."""

import pytest
from PIL import Image

from app.domain.enums import AttachmentKind
from app.domain.exceptions import AttachmentExceedsLimitError, AttachmentParseError
from app.infrastructure.attachments.image import parse_image_attachment
from tests.unit.infrastructure.attachments.fixtures import (
    attachment_content,
    jpeg_with_exif_secret,
    png_with_dimensions,
    tiny_jpeg,
    tiny_png,
)


def test_valid_jpeg_prepares_image_input() -> None:
    parsed = parse_image_attachment(
        attachment_content(tiny_jpeg(), filename="photo.jpg", media_type="image/jpeg"),
        AttachmentKind.JPEG,
    )

    assert parsed.kind is AttachmentKind.JPEG
    assert parsed.extracted_text is None
    assert parsed.image is not None
    assert parsed.image.media_type == "image/jpeg"
    assert parsed.image.content.startswith(b"\xff\xd8\xff")
    Image.open(__import__("io").BytesIO(parsed.image.content)).verify()


def test_valid_png_prepares_image_input() -> None:
    parsed = parse_image_attachment(
        attachment_content(tiny_png(), filename="chart.png", media_type="image/png"),
        AttachmentKind.PNG,
    )

    assert parsed.kind is AttachmentKind.PNG
    assert parsed.image is not None
    assert parsed.image.media_type == "image/png"
    assert parsed.image.content.startswith(b"\x89PNG\r\n\x1a\n")


def test_image_rejects_more_than_20_megapixels() -> None:
    payload = png_with_dimensions(5000, 5000)
    with pytest.raises(AttachmentExceedsLimitError):
        parse_image_attachment(
            attachment_content(payload, filename="huge.png", media_type="image/png"),
            AttachmentKind.PNG,
        )


def test_image_rejects_malformed() -> None:
    with pytest.raises(AttachmentParseError):
        parse_image_attachment(
            attachment_content(
                b"\xff\xd8\xff\xe0not-a-jpeg",
                filename="bad.jpg",
                media_type="image/jpeg",
            ),
            AttachmentKind.JPEG,
        )


def test_image_decompression_bomb_path() -> None:
    payload = png_with_dimensions(20000, 20000)
    with pytest.raises(AttachmentExceedsLimitError):
        parse_image_attachment(
            attachment_content(payload, filename="bomb.png", media_type="image/png"),
            AttachmentKind.PNG,
        )


def test_image_does_not_forward_exif() -> None:
    secret = b"ECI-EXIF-GPS-SECRET"
    original = jpeg_with_exif_secret(secret)
    assert secret in original
    parsed = parse_image_attachment(
        attachment_content(original, filename="geo.jpg", media_type="image/jpeg"),
        AttachmentKind.JPEG,
    )

    assert parsed.image is not None
    assert secret not in parsed.image.content
    assert "image_exif_stripped" in parsed.warnings
