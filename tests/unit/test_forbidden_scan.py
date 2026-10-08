"""«Сканер запрещённого» (T8.08, docs/06, docs/02): в коде нет того, что вне MVP или запрещено.

Тест идёт в CI вместе с остальными. Проверка: добавьте в ``src`` строку ``import requests``,
тест покраснеет.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
FRONTEND = ROOT / "frontend"

# Функции долгов и баланса вне MVP (docs/01 §4.3: «Баланса занятий и списка должников нет»);
# argon2, Flet, Arq, JWT — не входят в стек (docs/02).
FORBIDDEN_WORDS = re.compile(
    r"(?<![A-Za-z])(?:balance|debtors?|argon2|flet|arq|jwt)(?![A-Za-z])", re.IGNORECASE
)
# Слово «balance» — в перечне финансовых терминов, по которым тест приватности ищет деньги
# в схемах ответов. Это защита, а не функция баланса.
WORD_ALLOWLIST = {"src/schemas/roles.py"}

FORBIDDEN_IMPORT = re.compile(r"^\s*(?:import|from)\s+(boto3|requests|psycopg2)\b", re.MULTILINE)
AIOGRAM_IMPORT = re.compile(r"^\s*(?:import|from)\s+aiogram\b", re.MULTILINE)
FRONTEND_TYPE_ESCAPES = re.compile(
    r":\s*any\b|\bas any\b|<any>|\bany\[\]|@ts-ignore|@ts-nocheck|@ts-expect-error"
)


def python_files(base: Path) -> list[Path]:
    return [path for path in base.rglob("*.py") if "__pycache__" not in path.parts]


def frontend_files() -> list[Path]:
    files: list[Path] = []
    for base in (FRONTEND / "src", FRONTEND / "e2e"):
        files += [
            path
            for path in base.rglob("*")
            if path.suffix in {".ts", ".tsx"} and path.name != "schema.d.ts"
        ]
    return files


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def test_no_forbidden_words_in_backend_and_frontend() -> None:
    hits = [
        f"{relative(path)}: {match.group(0)}"
        for path in [*python_files(SRC), *frontend_files()]
        if relative(path) not in WORD_ALLOWLIST
        for match in FORBIDDEN_WORDS.finditer(path.read_text(encoding="utf-8"))
    ]

    assert hits == []


def test_no_forbidden_python_packages() -> None:
    hits = [
        f"{relative(path)}: {match.group(1)}"
        for path in python_files(SRC)
        for match in FORBIDDEN_IMPORT.finditer(path.read_text(encoding="utf-8"))
    ]

    assert hits == []


def test_services_do_not_import_aiogram() -> None:
    """Слой сервисов не знает про Telegram: бот вызывает сервисы, а не наоборот (docs/03)."""
    hits = [
        relative(path)
        for path in python_files(SRC / "services")
        if AIOGRAM_IMPORT.search(path.read_text(encoding="utf-8"))
    ]

    assert hits == []


def test_frontend_has_no_any_or_ts_ignore() -> None:
    hits = [
        f"{relative(path)}: {match.group(0)}"
        for path in frontend_files()
        for match in FRONTEND_TYPE_ESCAPES.finditer(path.read_text(encoding="utf-8"))
    ]

    assert hits == []


def test_scan_actually_detects_violations() -> None:
    """Сам сканер не пустой: на заведомо плохих строках срабатывает."""
    assert FORBIDDEN_WORDS.search("def get_balance(): ...")
    assert FORBIDDEN_WORDS.search("import jwt")
    assert FORBIDDEN_IMPORT.search("import requests\n")
    assert FORBIDDEN_IMPORT.search("from boto3 import client\n")
    assert AIOGRAM_IMPORT.search("from aiogram import Bot\n")
    assert FRONTEND_TYPE_ESCAPES.search("const value: any = 1;")
    assert FRONTEND_TYPE_ESCAPES.search("// @ts-ignore")
    assert not FORBIDDEN_WORDS.search("balanced tree")
    assert len(python_files(SRC)) > 100
    assert len(frontend_files()) > 100
