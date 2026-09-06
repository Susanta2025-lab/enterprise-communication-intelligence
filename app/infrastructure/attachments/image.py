"""Safe JPEG/PNG preparation. EXIF is stripped. OCR is not performed."""

from __future__ import annotations

import io
import warnings

from PIL import Image, UnidentifiedImageError
from PIL.Image import DecompressionBombError, DecompressionBombWarning

from app.domain.attachment_policy import (
    MAX_IMAGE_DIMENSION,
    MAX_IMAGE_PIXELS,
    MAX_IMAGE_UNCOMPRESSED_BYTES,
)
from app.domain.enums import AttachmentKind
from app.domain.exceptions import (
    AttachmentExceedsLimitError,
    AttachmentParseError,
)
from app.domain.models.attachment import AIImageInput, AttachmentContent, ParsedAttachment

Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

_KIND_MEDIA_TYPES = {
    AttachmentKind.JPEG: "image/jpeg",
    AttachmentKind.PNG: "image/png",
}


def parse_image_attachment(
    content: AttachmentContent,
    kind: AttachmentKind,
) -> ParsedAttachment:
    """Decode one JPEG or PNG, enforce pixel bounds, and strip EXIF."""
    if kind not in {AttachmentKind.JPEG, AttachmentKind.PNG}:
        raise AttachmentParseError()

    payload = content.content
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", DecompressionBombWarning)
            with Image.open(io.BytesIO(payload)) as verified:
                verified.verify()
    except (
        UnidentifiedImageError,
        DecompressionBombError,
        DecompressionBombWarning,
        OSError,
        ValueError,
        SyntaxError,
    ) as exc:
        if isinstance(exc, (DecompressionBombError, DecompressionBombWarning)):
            raise AttachmentExceedsLimitError() from exc
        raise AttachmentParseError() from exc

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", DecompressionBombWarning)
            with Image.open(io.BytesIO(payload)) as image:
                width, height = image.size
                _reject_oversized_image(width, height)
                image.load()
                prepared = _exif_stripped_copy(image)
                encoded = _encode_without_exif(prepared, kind)
    except DecompressionBombError as exc:
        raise AttachmentExceedsLimitError() from exc
    except DecompressionBombWarning as exc:
        raise AttachmentExceedsLimitError() from exc
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise AttachmentParseError() from exc

    media_type = _KIND_MEDIA_TYPES[kind]
    return ParsedAttachment(
        kind=kind,
        media_type=media_type,
        extracted_text=None,
        page_count=None,
        character_count=0,
        truncated=False,
        warnings=("image_exif_stripped",),
        image=AIImageInput(media_type=media_type, content=encoded),
    )


def _reject_oversized_image(width: int, height: int) -> None:
    if width <= 0 or height <= 0:
        raise AttachmentParseError()
    if width > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION:
        raise AttachmentExceedsLimitError()
    if width * height > MAX_IMAGE_PIXELS:
        raise AttachmentExceedsLimitError()
    if width * height * 4 > MAX_IMAGE_UNCOMPRESSED_BYTES:
        raise AttachmentExceedsLimitError()


def _exif_stripped_copy(image: Image.Image) -> Image.Image:
    mode = "RGB" if image.mode not in {"RGB", "L", "RGBA"} else image.mode
    converted = image.convert(mode)
    clean = Image.new(converted.mode, converted.size)
    clean.paste(converted)
    return clean


def _encode_without_exif(image: Image.Image, kind: AttachmentKind) -> bytes:
    buffer = io.BytesIO()
    if kind is AttachmentKind.JPEG:
        if image.mode not in {"RGB", "L"}:
            image = image.convert("RGB")
        image.save(buffer, format="JPEG", quality=90)
    else:
        image.save(buffer, format="PNG")
    return buffer.getvalue()
