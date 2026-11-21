"""Перевірка й очищення фото заявки (DQ-04, п. 3.2 «Очищення фото»).

- до 3 фото, кожне до 5 МБ;
- формат визначається за вмістом файлу, а не за розширенням: лише JPEG, PNG, WebP;
- зображення перезберігається без метаданих EXIF (GPS, модель пристрою, час),
  а поворот з EXIF застосовується до самого зображення, щоб фото не «лягло на бік».
"""

from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_PHOTOS = 3
MAX_PHOTO_BYTES = 5 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 50_000_000  # захист від «бомб» з величезною роздільністю

FORMATS = {
    "JPEG": ("image/jpeg", "jpg"),
    "PNG": ("image/png", "png"),
    "WEBP": ("image/webp", "webp"),
}


class PhotoError(ValueError):
    """Фото не пройшло перевірку; повідомлення містить назву файлу."""


@dataclass(frozen=True)
class CleanPhoto:
    mime_type: str
    extension: str
    data: bytes


def clean_photo(filename: str, raw: bytes) -> CleanPhoto:
    if len(raw) == 0:
        raise PhotoError(f"{filename}: файл порожній")
    if len(raw) > MAX_PHOTO_BYTES:
        raise PhotoError(f"{filename}: розмір понад 5 МБ")
    try:
        image = Image.open(BytesIO(raw))
        fmt = image.format
        if fmt not in FORMATS:
            raise PhotoError(f"{filename}: дозволені лише JPEG, PNG або WebP")
        image.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise PhotoError(f"{filename}: файл не є зображенням JPEG, PNG або WebP") from exc

    image = ImageOps.exif_transpose(image)
    for key in ("exif", "xmp", "XML:com.adobe.xmp", "comment"):
        image.info.pop(key, None)
    out = BytesIO()
    if fmt == "JPEG":
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        image.save(out, "JPEG", quality=90)
    elif fmt == "WEBP":
        image.save(out, "WEBP", quality=90)
    else:
        image.save(out, "PNG", optimize=True)

    data = out.getvalue()
    if len(data) > MAX_PHOTO_BYTES:
        raise PhotoError(f"{filename}: розмір понад 5 МБ")
    mime_type, extension = FORMATS[fmt]
    return CleanPhoto(mime_type=mime_type, extension=extension, data=data)
