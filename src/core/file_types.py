"""Определение типа файла по СОДЕРЖИМОМУ (magic bytes), а не по расширению (T4.05, docs/09).

Расширение и ``Content-Type`` из запроса подделываются тривиально: файл ``.jpg`` с содержимым
исполняемого файла не должен пройти. Поэтому тип берётся из первых байтов.
"""

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_SOLUTION_FILES = 10
IMAGE_MAX_SIDE = 2400
JPEG_QUALITY = 85

JPEG = "image/jpeg"
PNG = "image/png"
HEIC = "image/heic"
PDF = "application/pdf"

ALLOWED_TYPES = frozenset({JPEG, PNG, HEIC, PDF})
IMAGE_TYPES = frozenset({JPEG, PNG, HEIC})

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_HEIC_BRANDS = frozenset({b"heic", b"heix", b"heim", b"heis", b"hevc", b"hevx", b"mif1", b"msf1"})
_FTYP_OFFSET = 4
_BRAND_OFFSET = 8
_BRAND_END = 12


def detect_content_type(data: bytes) -> str | None:
    """Тип файла по первым байтам: JPEG, PNG, HEIC, PDF; иное содержимое — ``None``."""
    if data.startswith(b"\xff\xd8\xff"):
        return JPEG
    if data.startswith(_PNG_SIGNATURE):
        return PNG
    if data.startswith(b"%PDF-"):
        return PDF
    if (
        data[_FTYP_OFFSET:_BRAND_OFFSET] == b"ftyp"
        and data[_BRAND_OFFSET:_BRAND_END] in _HEIC_BRANDS
    ):
        return HEIC
    return None
