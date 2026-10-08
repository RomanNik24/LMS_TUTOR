"""Конвертация первичных баллов пробников (T6.02, docs/04 §6 и §10, docs/01 US-06).

Ожидаемые значения записаны здесь по таблицам docs/04 §10 (не берутся из сидов): тест проверяет и
сервис, и данные шкал.
"""

from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.models import ExamType, GradeScale
from src.schemas.exams import ConversionWarning
from src.services.exams import ExamService

EXAM_2026 = date(2026, 5, 20)

# (код экзамена, первичный балл, ожидаемый результат): границы всех четырёх шкал, docs/04 §10
BOUNDARIES = [
    # ОГЭ информатика: 2 | 0–4, 3 | 5–10, 4 | 11–16, 5 | 17–21
    ("oge_informatics", 0, 2),
    ("oge_informatics", 4, 2),
    ("oge_informatics", 5, 3),
    ("oge_informatics", 10, 3),
    ("oge_informatics", 11, 4),
    ("oge_informatics", 16, 4),
    ("oge_informatics", 17, 5),
    ("oge_informatics", 21, 5),
    # ОГЭ математика (геометрия не указана): 2 | 0–7, 3 | 8–14, 4 | 15–21, 5 | 22–31
    ("oge_math", 7, 2),
    ("oge_math", 8, 3),
    ("oge_math", 14, 3),
    ("oge_math", 15, 4),
    ("oge_math", 21, 4),
    ("oge_math", 22, 5),
    ("oge_math", 31, 5),
    # ЕГЭ информатика (порог аттестата: 6 первичных = 40 тестовых)
    ("ege_informatics", 0, 0),
    ("ege_informatics", 1, 7),
    ("ege_informatics", 5, 34),
    ("ege_informatics", 6, 40),
    ("ege_informatics", 10, 51),
    ("ege_informatics", 20, 78),
    ("ege_informatics", 27, 95),
    ("ege_informatics", 29, 100),
    # ЕГЭ математика профильная (порог аттестата: 5 первичных = 27 тестовых)
    ("ege_math_profile", 0, 0),
    ("ege_math_profile", 4, 22),
    ("ege_math_profile", 5, 27),
    ("ege_math_profile", 6, 34),
    ("ege_math_profile", 11, 64),
    ("ege_math_profile", 21, 88),
    ("ege_math_profile", 30, 100),
    ("ege_math_profile", 32, 100),
]


@pytest.mark.parametrize(("code", "primary", "expected"), BOUNDARIES)
async def test_scale_boundaries(
    db_session: AsyncSession,
    seeded_reference: dict[str, ExamType],
    code: str,
    primary: int,
    expected: int,
) -> None:
    exam_type = seeded_reference[code]
    result = await ExamService(db_session).convert_score(
        exam_type, exam_date=EXAM_2026, primary_score=primary, max_primary=exam_type.max_primary
    )
    assert (result.converted_value, result.scale_year, result.scale_applicable) == (
        expected,
        2026,
        True,
    )
    # у ОГЭ математики без баллов по геометрии расчёт идёт по сумме, с предупреждением
    assert result.warning == (ConversionWarning.GEOMETRY_MISSING if code == "oge_math" else None)


@pytest.mark.parametrize(
    ("geometry", "primary", "expected", "warning"),
    [
        (1, 22, 2, None),  # сумма даёт «5», но геометрии меньше 2: оценка 2
        (0, 31, 2, None),
        (1, 15, 2, None),
        (2, 22, 5, None),  # ровно 2 балла по геометрии: правило не срабатывает
        (2, 8, 3, None),
        (0, 7, 2, None),  # сумма 0–7 и так даёт «2»
        (None, 22, 5, ConversionWarning.GEOMETRY_MISSING),  # не указано: расчёт по сумме
    ],
)
async def test_oge_math_geometry_rule(
    db_session: AsyncSession,
    seeded_reference: dict[str, ExamType],
    geometry: int | None,
    primary: int,
    expected: int,
    warning: ConversionWarning | None,
) -> None:
    exam_type = seeded_reference["oge_math"]
    result = await ExamService(db_session).convert_score(
        exam_type,
        exam_date=EXAM_2026,
        primary_score=primary,
        max_primary=31,
        geometry_score=geometry,
    )
    assert result.converted_value == expected
    assert result.scale_applicable is True
    assert result.warning == warning


async def test_geometry_does_not_affect_other_exams(
    db_session: AsyncSession, seeded_reference: dict[str, ExamType]
) -> None:
    exam_type = seeded_reference["oge_informatics"]
    result = await ExamService(db_session).convert_score(
        exam_type, exam_date=EXAM_2026, primary_score=17, max_primary=21, geometry_score=0
    )
    assert (result.converted_value, result.warning) == (5, None)


async def test_exam_with_27_points_of_ege_informatics_has_no_scale(
    db_session: AsyncSession, seeded_reference: dict[str, ExamType]
) -> None:
    """Пример docs/04 §10.4: «пробник на 27 баллов» — максимум 27 вместо 29, шкала неприменима."""
    exam_type = seeded_reference["ege_informatics"]
    result = await ExamService(db_session).convert_score(
        exam_type, exam_date=EXAM_2026, primary_score=20, max_primary=27
    )
    assert result.model_dump() == {
        "converted_value": None,
        "scale_year": None,
        "scale_applicable": False,
        "warning": None,
    }


async def test_scale_of_latest_year_not_after_exam_year_is_used(
    db_session: AsyncSession, seeded_reference: dict[str, ExamType]
) -> None:
    """Берётся шкала с максимальным valid_year <= год экзамена; шкал нет — не применима."""
    exam_type = seeded_reference["oge_informatics"]
    db_session.add_all(
        GradeScale(
            exam_type_id=exam_type.id,
            valid_year=2028,
            primary_score=primary,
            result_value=value,
        )
        for primary, value in ((10, 4), (11, 5))
    )
    await db_session.commit()
    service = ExamService(db_session)

    async def convert(day: date, primary: int) -> tuple[int | None, int | None]:
        result = await service.convert_score(
            exam_type, exam_date=day, primary_score=primary, max_primary=21
        )
        return result.converted_value, result.scale_year

    assert await convert(date(2026, 12, 31), 10) == (3, 2026)
    assert await convert(date(2027, 6, 1), 10) == (3, 2026)  # 2027 шкалы нет → 2026
    assert await convert(date(2028, 1, 1), 10) == (4, 2028)  # новая шкала действует с 2028
    assert await convert(date(2029, 5, 1), 11) == (5, 2028)
    assert await convert(date(2025, 5, 1), 10) == (None, None)  # шкал до 2026 нет


async def test_primary_score_missing_in_scale_is_not_applicable(
    db_session: AsyncSession, seeded_reference: dict[str, ExamType]
) -> None:
    exam_type = seeded_reference["oge_informatics"]
    result = await ExamService(db_session).convert_score(
        exam_type, exam_date=EXAM_2026, primary_score=99, max_primary=21
    )
    assert result.scale_applicable is False
    assert result.converted_value is None
