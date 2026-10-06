"""Выгрузка ``openapi.json`` без запуска сервера (задача T1.10, docs/03 §14).

Использование: ``uv run python scripts/export_openapi.py <путь_вывода>``.
Схема строится из Pydantic-моделей приложения; БД, Redis и переменные
окружения для этого не нужны. Из файла фронтенд генерирует типы (``pnpm gen:api``).
"""

import json
import sys
from pathlib import Path

# Позволяет запускать скрипт напрямую: корень репозитория — в sys.path.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.main import create_app  # noqa: E402


def main(argv: list[str]) -> int:
    """Записать OpenAPI-схему в файл, указанный первым аргументом."""
    if len(argv) != 2:
        print("Использование: export_openapi.py <путь_вывода>")
        return 2
    output = Path(argv[1])
    # Схема не зависит от окружения; локальная сборка приложения включает все роутеры.
    schema = create_app("local").openapi()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"OpenAPI записан: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
