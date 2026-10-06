"""Юнит-тесты справочных сидов T1.03 (без подключения к БД).

Проверяют:

- полноту шкал grade_scales 2026 по docs/04 §10
  (ЕГЭ информатика 0–29 = 30 строк; ЕГЭ профильная математика 0–32 = 33;
  ОГЭ информатика 0–21 = 22; ОГЭ математика 0–31 = 32);
- корректность составов subjects / exam_types (включая config
  ``{"min_geometry": 2}`` для ОГЭ математики);
- наличие обязательной пометки «ожидает сверки владельцем».

Комментарии на русском согласно docs/06_agent_rules.md.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from src.db.seeds.reference import (
    EXAM_TYPES,
    EXPECTED_SCALE_LENGTHS,
    GRADE_SCALES,
    SCALE_YEAR,
    SUBJECTS,
)

# Границы первичных баллов по docs/04 §10: код экзамена -> максимальный балл.
MAX_PRIMARY_BY_CODE: dict[str, int] = {
    "oge_informatics": 21,  # §10.1
    "oge_math": 31,  # §10.2
    "ege_informatics": 29,  # §10.3
    "ege_math_profile": 32,  # §10.4
}


def test_subjects_are_two_expected_codes() -> None:
    """docs/04 §9: предметы ровно два — informatics и math."""
    codes = [str(s["code"]) for s in SUBJECTS]
    assert sorted(codes) == ["informatics", "math"]


def test_exam_types_are_four_with_valid_subject_refs() -> None:
    """docs/04 §9–§10: четыре типа экзамена, ссылки на существующие предметы."""
    assert len(EXAM_TYPES) == 4
    subject_codes = {str(s["code"]) for s in SUBJECTS}
    exam_codes = {str(e["code"]) for e in EXAM_TYPES}
    assert exam_codes == set(GRADE_SCALES)
    for row in EXAM_TYPES:
        assert str(row["subject_code"]) in subject_codes
        assert str(row["kind"]) in {"oge", "ege"}
        assert str(row["result_kind"]) in {"grade_2_5", "test_100"}


def test_oge_math_config_requires_min_geometry() -> None:
    """docs/04 §10.2: у ОГЭ математики config = {"min_geometry": 2}."""
    oge_math = next(e for e in EXAM_TYPES if e["code"] == "oge_math")
    assert oge_math["config"] == {"min_geometry": 2}


@pytest.mark.parametrize("exam_code", sorted(EXPECTED_SCALE_LENGTHS))
def test_grade_scale_is_complete_and_contiguous(exam_code: str) -> None:
    """Шкала покрыла все первичные баллы 0..max_primary без пропусков и дублей.

    Полнота по задаче T1.03: ЕГЭ информатика 0–29 = 30 строк;
    ЕГЭ профильная математика 0–32 = 33; ОГЭ информатика 0–21 = 22;
    ОГЭ математика 0–31 = 32.
    """
    scale = GRADE_SCALES[exam_code]
    max_primary = MAX_PRIMARY_BY_CODE[exam_code]

    # Ожидаемое число строк совпадает с постановкой задачи.
    assert len(scale) == EXPECTED_SCALE_LENGTHS[exam_code]
    # Каждый балл от 0 до max_primary включительно присутствует ровно один раз.
    assert sorted(scale) == list(range(max_primary + 1))


@pytest.mark.parametrize(
    ("exam_code", "primary", "expected"),
    [
        # docs/04 §10.1: границы оценок ОГЭ информатики (по письму 2026).
        ("oge_informatics", 4, 2),
        ("oge_informatics", 5, 3),
        ("oge_informatics", 10, 3),
        ("oge_informatics", 11, 4),
        ("oge_informatics", 16, 4),
        ("oge_informatics", 17, 5),
        ("oge_informatics", 21, 5),
        # docs/04 §10.2: границы оценок ОГЭ математики.
        ("oge_math", 7, 2),
        ("oge_math", 8, 3),
        ("oge_math", 15, 4),
        ("oge_math", 22, 5),
        ("oge_math", 31, 5),
        # docs/04 §10.3: выборочные точки шкалы ЕГЭ информатики.
        ("ege_informatics", 0, 0),
        ("ege_informatics", 6, 40),
        ("ege_informatics", 29, 100),
        # docs/04 §10.4: выборочные точки шкалы ЕГЭ профильной математики.
        ("ege_math_profile", 0, 0),
        ("ege_math_profile", 5, 27),
        ("ege_math_profile", 32, 100),
    ],
)
def test_grade_scale_boundary_values(exam_code: str, primary: int, expected: int) -> None:
    """Контрольные точки шкал точно соответствуют таблицам docs/04 §10."""
    assert GRADE_SCALES[exam_code][primary] == expected


@pytest.mark.parametrize("exam_code", sorted(EXPECTED_SCALE_LENGTHS))
def test_max_primary_matches_exam_type_and_scale(exam_code: str) -> None:
    """max_primary в exam_types совпадает с верхней границей шкалы (§10)."""
    exam = next(e for e in EXAM_TYPES if e["code"] == exam_code)
    scale = GRADE_SCALES[exam_code]
    assert exam["max_primary"] == MAX_PRIMARY_BY_CODE[exam_code]
    assert max(scale) == exam["max_primary"]


def test_scale_year_is_2026() -> None:
    """Сидим шкалы года действия 2026 (docs/04 §10)."""
    assert SCALE_YEAR == 2026


def test_seeds_marked_for_owner_verification() -> None:
    """Модуль сидов ОБЯЗАН содержать пометку «ожидает сверки владельцем»."""
    source = Path("src/db/seeds/reference.py").read_text(encoding="utf-8")
    assert "ожидает сверки владельцем" in source.lower()


def test_seed_script_is_idempotent_by_construction() -> None:
    """Скрипт сида использует ON CONFLICT DO NOTHING по всем трём таблицам.

    Это статическая гарантия идемпотентности: повторный запуск не создаёт
    дублей. Поведение на живой БД проверяется интеграционным тестом
    tests/integration/test_migration_and_seeds.py.
    """
    source = Path("scripts/seed_reference.py").read_text(encoding="utf-8")
    assert source.count("ON CONFLICT") >= 3
    assert "DO NOTHING" in source
