"""Обработка загруженных фотографий: HEIC → JPEG, поворот по EXIF, сжатие (T4.05, docs/09).

Работа Pillow синхронная и тяжёлая, поэтому ``prepare_image`` выполняет её в потоке
(``asyncio.to_thread``) и не блокирует event loop. Все растровые форматы приводятся к JPEG:
файл меньше, телефон и экран проверки открывают его одинаково.
"""

import asyncio
import io

import pillow_heif
from PIL import Image, ImageOps

from src.core.file_types import IMAGE_MAX_SIDE, JPEG_QUALITY

pillow_heif.register_heif_opener()
# Защита от «бомб расширения»: картинка в сотни мегапикселей не должна съесть память. Pillow сам
# только предупреждает до двойного лимита, поэтому размер проверяется явно до загрузки пикселей.
MAX_PIXELS = 60_000_000
Image.MAX_IMAGE_PIXELS = None  # собственная проверка ниже, без предупреждений Pillow


class ImageProcessingError(Exception):
    """Файл не удалось открыть как изображение (повреждён или слишком велик по пикселям)."""


def _normalize(data: bytes) -> bytes:
    try:
        with Image.open(io.BytesIO(data)) as source:
            if source.width * source.height > MAX_PIXELS:
                raise ImageProcessingError("Слишком большое изображение по числу пикселей")
            image = ImageOps.exif_transpose(source)
            image.load()
    except (OSError, ValueError, Image.DecompressionBombError) as error:
        raise ImageProcessingError(str(error)) from error
    if image.mode in ("RGBA", "LA", "P"):
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.split()[-1])
        image = background
    elif image.mode != "RGB":
        image = image.convert("RGB")
    image.thumbnail((IMAGE_MAX_SIDE, IMAGE_MAX_SIDE), Image.Resampling.LANCZOS)
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    return output.getvalue()


async def prepare_image(data: bytes) -> bytes:
    """JPEG из любого допустимого изображения: поворот по EXIF, длинная сторона ≤ 2400 px."""
    return await asyncio.to_thread(_normalize, data)
