"""Юнит-тесты справочных сидов T1.03 (без подключения к БД).

Проверяют:

- полноту шкал grade_scales 2026 по docs/04 §10
  (ЕГЭ информатика 0–29 = 30 строк; ЕГЭ профильная математика 0–32 = 33;
  ОГЭ информатика 0–21 = 22; ОГЭ математика 0–31 = 32);
- корректность состава subjects / exam_types;
- config ``{"min_geometry": 2}`` для ОГЭ математики;
- уникальность идентификационных ключей справочных данных.

Реальная идемпотентность ``scripts/seed_reference.py`` проверяется
интеграционными PostgreSQL-тестами T1.03.
"""

from __future__ import annotations

import pytest
from src.db.seeds.reference import (
    EXAM_TYPES,
    EXPECTED_SCALE_LENGTHS,
    GRADE_SCALES,
    SCALE_YEAR,
    SUBJECTS,
)

MAX_PRIMARY_BY_CODE: dict[str, int] = {
    "oge_informatics": 21,
    "oge_math": 31,
    "ege_informatics": 29,
    "ege_math_profile": 32,
}


def test_subjects_are_two_expected_codes() -> None:
    """docs/04 §9: предметы ровно два — informatics и math."""

    codes = [str(subject["code"]) for subject in SUBJECTS]
    assert sorted(codes) == ["informatics", "math"]


def test_exam_types_are_four_with_valid_subject_refs() -> None:
    """docs/04 §9–§10: четыре типа экзамена, ссылки на существующие предметы."""

    assert len(EXAM_TYPES) == 4
    subject_codes = {str(subject["code"]) for subject in SUBJECTS}
    exam_codes = {str(exam["code"]) for exam in EXAM_TYPES}

    assert exam_codes == {
        "oge_informatics",
        "oge_math",
        "ege_informatics",
        "ege_math_profile",
    }
    assert exam_codes == set(GRADE_SCALES)

    for exam in EXAM_TYPES:
        assert str(exam["subject_code"]) in subject_codes
        assert str(exam["kind"]) in {"oge", "ege"}
        assert str(exam["result_kind"]) in {"grade_2_5", "test_100"}


def test_oge_math_config_requires_min_geometry() -> None:
    """docs/04 §10.2: config ОГЭ математики содержит min_geometry = 2."""

    oge_math = next(exam for exam in EXAM_TYPES if exam["code"] == "oge_math")
    assert oge_math["config"] == {"min_geometry": 2}


@pytest.mark.parametrize("exam_code", sorted(EXPECTED_SCALE_LENGTHS))
def test_grade_scale_is_complete_and_contiguous(exam_code: str) -> None:
    """Шкала покрывает все первичные баллы 0..max_primary без пропусков."""

    scale = GRADE_SCALES[exam_code]
    max_primary = MAX_PRIMARY_BY_CODE[exam_code]

    assert len(scale) == EXPECTED_SCALE_LENGTHS[exam_code]
    assert sorted(scale) == list(range(max_primary + 1))


@pytest.mark.parametrize(
    ("exam_code", "primary", "expected"),
    [
        ("oge_informatics", 4, 2),
        ("oge_informatics", 5, 3),
        ("oge_informatics", 10, 3),
        ("oge_informatics", 11, 4),
        ("oge_informatics", 16, 4),
        ("oge_informatics", 17, 5),
        ("oge_informatics", 21, 5),
        ("oge_math", 7, 2),
        ("oge_math", 8, 3),
        ("oge_math", 15, 4),
        ("oge_math", 22, 5),
        ("oge_math", 31, 5),
        ("ege_informatics", 0, 0),
        ("ege_informatics", 6, 40),
        ("ege_informatics", 29, 100),
        ("ege_math_profile", 0, 0),
        ("ege_math_profile", 5, 27),
        ("ege_math_profile", 32, 100),
    ],
)
def test_grade_scale_boundary_values(exam_code: str, primary: int, expected: int) -> None:
    """Контрольные точки шкал соответствуют docs/04 §10."""

    assert GRADE_SCALES[exam_code][primary] == expected


@pytest.mark.parametrize("exam_code", sorted(EXPECTED_SCALE_LENGTHS))
def test_max_primary_matches_exam_type_and_scale(exam_code: str) -> None:
    """max_primary совпадает с верхней границей соответствующей шкалы."""

    exam = next(exam for exam in EXAM_TYPES if exam["code"] == exam_code)
    scale = GRADE_SCALES[exam_code]

    assert exam["max_primary"] == MAX_PRIMARY_BY_CODE[exam_code]
    assert max(scale) == exam["max_primary"]


def test_scale_year_is_2026() -> None:
    """Сидим шкалы года действия 2026."""

    assert SCALE_YEAR == 2026


def test_reference_seed_identity_keys_are_unique() -> None:
    """Идентификационные ключи справочников не содержат дубликатов."""

    subject_codes = [str(subject["code"]) for subject in SUBJECTS]
    exam_codes = [str(exam["code"]) for exam in EXAM_TYPES]

    assert len(subject_codes) == len(set(subject_codes))
    assert len(exam_codes) == len(set(exam_codes))

    for exam_code, scale in GRADE_SCALES.items():
        keys = list(scale)
        assert len(keys) == len(set(keys)), exam_code
