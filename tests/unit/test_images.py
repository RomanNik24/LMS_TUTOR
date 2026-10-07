"""Обработка фотографий: HEIC → JPEG, поворот, сжатие (T4.05)."""

import io

import pillow_heif
import pytest
from PIL import Image
from src.core.file_types import IMAGE_MAX_SIDE, JPEG, detect_content_type
from src.core.images import ImageProcessingError, prepare_image

pillow_heif.register_heif_opener()


def encode(image: Image.Image, fmt: str, **kwargs: object) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format=fmt, **kwargs)
    return buffer.getvalue()


def decode(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data))


async def test_heic_becomes_jpeg() -> None:
    source = encode(Image.new("RGB", (80, 60), (200, 30, 30)), "HEIF")
    assert detect_content_type(source) == "image/heic"
    result = await prepare_image(source)
    assert detect_content_type(result) == JPEG
    assert decode(result).size == (80, 60)


async def test_long_side_is_limited_and_aspect_kept() -> None:
    source = encode(Image.new("RGB", (4000, 3000), (10, 120, 200)), "JPEG")
    result = decode(await prepare_image(source))
    assert max(result.size) == IMAGE_MAX_SIDE
    assert result.size == (2400, 1800)


async def test_small_image_is_not_upscaled() -> None:
    source = encode(Image.new("RGB", (300, 200), "white"), "PNG")
    assert decode(await prepare_image(source)).size == (300, 200)


async def test_png_with_transparency_gets_white_background() -> None:
    source = encode(Image.new("RGBA", (20, 20), (0, 0, 0, 0)), "PNG")
    pixel = decode(await prepare_image(source)).convert("RGB").getpixel((5, 5))
    assert isinstance(pixel, tuple)
    assert min(pixel) >= 250


async def test_exif_orientation_is_applied() -> None:
    image = Image.new("RGB", (200, 100), "red")
    exif = Image.Exif()
    exif[0x0112] = 6  # повернуть на 90° по часовой при показе
    source = encode(image, "JPEG", exif=exif)
    assert decode(await prepare_image(source)).size == (100, 200)


async def test_grayscale_and_palette_modes_are_converted() -> None:
    for mode in ("L", "P"):
        source = encode(Image.new(mode, (30, 30)), "PNG")
        assert decode(await prepare_image(source)).mode == "RGB"


async def test_corrupted_image_raises() -> None:
    with pytest.raises(ImageProcessingError):
        await prepare_image(b"\xff\xd8\xff\xe0" + b"garbage" * 10)


async def test_decompression_bomb_is_rejected() -> None:
    # 9000x9000 = 81 млн пикселей: больше лимита в 60 млн, в файле при этом считанные килобайты
    bomb = encode(Image.new("1", (9000, 9000)), "PNG")
    assert len(bomb) < 1_000_000
    with pytest.raises(ImageProcessingError):
        await prepare_image(bomb)
