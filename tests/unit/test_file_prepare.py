"""Проверка загружаемого файла: тип по содержимому, размер, имя (T4.05)."""

import io

import pytest
from PIL import Image
from src.core.exceptions import AppError, ValidationError
from src.core.file_types import MAX_FILE_BYTES
from src.services.files import display_name, prepare_upload

PDF_BYTES = b"%PDF-1.4\n" + b"x" * 100


def png(size: tuple[int, int] = (50, 50)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, "blue").save(buffer, format="PNG")
    return buffer.getvalue()


async def test_image_is_converted_to_jpeg_with_jpg_extension() -> None:
    prepared = await prepare_upload("решение.png", png())
    assert prepared.content_type == "image/jpeg"
    assert prepared.extension == "jpg"
    assert prepared.name == "решение.png"


async def test_pdf_is_kept_as_is() -> None:
    prepared = await prepare_upload("задача.pdf", PDF_BYTES)
    assert prepared.data == PDF_BYTES
    assert (prepared.content_type, prepared.extension) == ("application/pdf", "pdf")


async def test_jpg_extension_with_executable_content_is_415() -> None:
    with pytest.raises(AppError) as raised:
        await prepare_upload("photo.jpg", b"MZ\x90\x00" + b"\x00" * 200)
    assert raised.value.http_status == 415
    assert raised.value.code == "unsupported_file_type"


async def test_png_extension_with_pdf_content_is_still_a_pdf() -> None:
    prepared = await prepare_upload("fake.png", PDF_BYTES)
    assert prepared.content_type == "application/pdf"


async def test_corrupted_image_is_415() -> None:
    with pytest.raises(AppError) as raised:
        await prepare_upload("a.jpg", b"\xff\xd8\xff\xe0" + b"junk" * 20)
    assert raised.value.http_status == 415


async def test_file_over_10_mb_is_413() -> None:
    with pytest.raises(AppError) as raised:
        await prepare_upload("big.pdf", PDF_BYTES + b"0" * MAX_FILE_BYTES)
    assert raised.value.http_status == 413
    assert raised.value.code == "file_too_large"


async def test_file_of_exactly_10_mb_is_allowed() -> None:
    data = PDF_BYTES + b"0" * (MAX_FILE_BYTES - len(PDF_BYTES))
    assert len(data) == MAX_FILE_BYTES
    assert (await prepare_upload("ok.pdf", data)).content_type == "application/pdf"


async def test_empty_file_is_rejected() -> None:
    with pytest.raises(ValidationError) as raised:
        await prepare_upload("a.pdf", b"")
    assert raised.value.code == "empty_file"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("../../etc/passwd", "passwd"),
        ("C:\\Users\\me\\hw.jpg", "hw.jpg"),
        ("a\x00b\nc.pdf", "abc.pdf"),
        ("   ", "файл"),
        ("", "файл"),
        ("я" * 400, "я" * 255),
    ],
)
def test_display_name_is_sanitized(raw: str, expected: str) -> None:
    assert display_name(raw) == expected
