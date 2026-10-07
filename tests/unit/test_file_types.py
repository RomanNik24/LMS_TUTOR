"""Определение типа файла по содержимому (T4.05)."""

import pytest
from src.core.file_types import HEIC, JPEG, PDF, PNG, detect_content_type

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20


def heic(brand: bytes) -> bytes:
    return b"\x00\x00\x00\x18ftyp" + brand + b"\x00" * 12


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (b"\xff\xd8\xff\xe0" + b"\x00" * 16, JPEG),
        (PNG_BYTES, PNG),
        (b"%PDF-1.7\n%" + b"\x00" * 10, PDF),
        (heic(b"heic"), HEIC),
        (heic(b"heix"), HEIC),
        (heic(b"mif1"), HEIC),
    ],
)
def test_known_types(data: bytes, expected: str) -> None:
    assert detect_content_type(data) == expected


@pytest.mark.parametrize(
    "data",
    [
        b"MZ\x90\x00" + b"\x00" * 40,  # исполняемый файл Windows
        b"\x7fELF" + b"\x00" * 40,  # исполняемый файл Linux
        b"#!/bin/sh\nrm -rf /\n",
        b"<script>alert(1)</script>",
        b"GIF89a" + b"\x00" * 10,  # GIF не входит в разрешённые типы
        b"PK\x03\x04" + b"\x00" * 10,  # zip
        b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 12,  # видео mp4: другой бренд ftyp
        b"",
        b"\xff\xd8",
    ],
)
def test_unknown_content_is_rejected(data: bytes) -> None:
    assert detect_content_type(data) is None
