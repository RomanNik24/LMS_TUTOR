"""Каждый код ошибки API имеет понятный текст во фронтенде (T8.05, docs/08 §1)."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CODE = re.compile(r"""code=["']([a-z_]+)["']""")
UI_KEY = re.compile(r"^ {4}([a-z_]+):", re.MULTILINE)
# Общие коды, которые отдают обработчики ошибок (src/api/errors.py), а не сервисы
GENERIC = {"unknown", "network"}


def backend_codes() -> set[str]:
    found: set[str] = set()
    for path in (ROOT / "src").rglob("*.py"):
        found |= set(CODE.findall(path.read_text(encoding="utf-8")))
    return found


def ui_error_keys() -> set[str]:
    source = (ROOT / "frontend/src/lib/texts.ts").read_text(encoding="utf-8")
    block = source[source.index("\n  errors: {") :]
    block = block[: block.index("\n  },")]
    return set(UI_KEY.findall(block)) | GENERIC


def test_every_backend_error_code_has_a_ui_text() -> None:
    missing = sorted(backend_codes() - ui_error_keys())

    assert missing == [], f"нет текста в frontend/src/lib/texts.ts → errors: {missing}"


def test_backend_codes_are_found() -> None:
    assert len(backend_codes()) > 50
