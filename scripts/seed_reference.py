"""Идемпотентный сид справочников (задача T1.03).

Заполняет таблицы ``subjects``, ``exam_types`` и ``grade_scales`` данными из
версионируемого файла ``src/db/seeds/reference.py`` (docs/04 §9–§10).

Идемпотентность: все вставки используют ``ON CONFLICT DO NOTHING`` по
уникальным ключам (``subjects.code``, ``exam_types.code``,
``grade_scales (exam_type_id, valid_year, primary_score)``), поэтому повторный
запуск скрипта НЕ создаёт дублей и не меняет количество строк.

Запуск: ``uv run python scripts/seed_reference.py`` (DATABASE_URL из .env).

Шкалы 2026 приняты владельцем (ADR 0004, docs/04 §10).

Комментарии на русском согласно docs/06_agent_rules.md.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# Позволяет запускать скрипт напрямую (python scripts/seed_reference.py):
# добавляем корень репозитория в sys.path до импорта пакетов src.*.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ruff: E402 — импорты проекта намеренно идут после настройки sys.path.
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402
from src.core.config import Settings  # noqa: E402
from src.db.seeds.reference import (  # noqa: E402
    EXAM_TYPES,
    GRADE_SCALES,
    SCALE_YEAR,
    SUBJECTS,
)


async def seed(database_url: str) -> dict[str, int]:
    """Загрузить справочники в БД; идемпотентно (без дублей при повторе).

    Args:
        database_url: строка подключения asyncpg (``postgresql+asyncpg://...``).

    Returns:
        Счётчики фактически вставленных строк по каждой таблице — удобно для
        логов и тестов идемпотентности (повтор даёт нули).
    """
    engine = create_async_engine(database_url)
    inserted = {"subjects": 0, "exam_types": 0, "grade_scales": 0}
    try:
        async with engine.begin() as conn:
            # --- subjects ----------------------------------------------------
            subject_ids: dict[str, int] = {}
            for row in SUBJECTS:
                res = await conn.execute(
                    text(
                        "INSERT INTO subjects (code, name)"
                        " VALUES (:code, :name)"
                        " ON CONFLICT (code) DO NOTHING"
                        " RETURNING id"
                    ),
                    {"code": row["code"], "name": row["name"]},
                )
                new_id = res.scalar()
                if new_id is not None:
                    inserted["subjects"] += 1
                    subject_ids[str(row["code"])] = int(new_id)
            # Докидываем id уже существующих записей (повторный запуск).
            res = await conn.execute(
                text("SELECT id, code FROM subjects WHERE code = ANY(:codes)"),
                {"codes": [str(r["code"]) for r in SUBJECTS]},
            )
            for ident, code in res.fetchall():
                subject_ids[str(code)] = int(ident)

            # --- exam_types --------------------------------------------------
            exam_type_ids: dict[str, int] = {}
            for row in EXAM_TYPES:
                res = await conn.execute(
                    text(
                        "INSERT INTO exam_types"
                        " (code, subject_id, kind, result_kind, max_primary,"
                        "  name, config)"
                        " VALUES (:code, :subject_id, :kind, :result_kind,"
                        "  :max_primary, :name, CAST(:config AS jsonb))"
                        " ON CONFLICT (code) DO NOTHING"
                        " RETURNING id"
                    ),
                    {
                        "code": row["code"],
                        "subject_id": subject_ids[str(row["subject_code"])],
                        "kind": row["kind"],
                        "result_kind": row["result_kind"],
                        "max_primary": row["max_primary"],
                        "name": row["name"],
                        "config": json.dumps(row["config"]),
                    },
                )
                new_id = res.scalar()
                if new_id is not None:
                    inserted["exam_types"] += 1
                    exam_type_ids[str(row["code"])] = int(new_id)
            res = await conn.execute(
                text("SELECT id, code FROM exam_types WHERE code = ANY(:codes)"),
                {"codes": [str(r["code"]) for r in EXAM_TYPES]},
            )
            for ident, code in res.fetchall():
                exam_type_ids[str(code)] = int(ident)

            # --- grade_scales (шкалы 2026, ADR 0004) --------
            scale_rows: list[dict[str, object]] = []
            for exam_code, scale in GRADE_SCALES.items():
                for primary_score, result_value in sorted(scale.items()):
                    scale_rows.append(
                        {
                            "exam_type_id": exam_type_ids[exam_code],
                            "valid_year": SCALE_YEAR,
                            "primary_score": primary_score,
                            "result_value": result_value,
                        }
                    )
            # Вставляем построчно: executemany + RETURNING не поддерживается
            # asyncpg; rowcount у одиночного INSERT надёжно отражает вставку.
            insert_stmt = text(
                "INSERT INTO grade_scales"
                " (exam_type_id, valid_year, primary_score, result_value)"
                " VALUES (:exam_type_id, :valid_year, :primary_score,"
                "  :result_value)"
                " ON CONFLICT (exam_type_id, valid_year, primary_score)"
                " DO NOTHING"
            )
            for row in scale_rows:
                res = await conn.execute(insert_stmt, row)
                if res.rowcount and res.rowcount > 0:
                    inserted["grade_scales"] += 1
    finally:
        await engine.dispose()
    return inserted


def main() -> None:
    """Точка входа CLI: берёт DATABASE_URL из Settings и печатает счётчики."""
    settings = Settings()
    inserted = asyncio.run(seed(settings.database_url))
    print(
        "Сид справочников выполнен (вставлено строк): "
        f"subjects={inserted['subjects']}, "
        f"exam_types={inserted['exam_types']}, "
        f"grade_scales={inserted['grade_scales']}. "
        "Повторный запуск добавляет 0 — идемпотентно."
    )


if __name__ == "__main__":
    main()
