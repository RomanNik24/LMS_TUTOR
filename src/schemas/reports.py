"""Схемы отчётов по ученику (docs/04 §11, docs/08 §4 и §5.2).

Финансовых полей в отчётах нет: это общая схема для ученика и персонала (docs/08 §8).
Проценты — целые, считает бэкенд: фронтенд только рисует (docs/06 B2).
"""

from datetime import date

from pydantic import BaseModel

from src.core.enums import ExamResultKind


class WeeklyHomeworkPoint(BaseModel):
    """Точка графика «Средний процент ДЗ»: ISO-неделя по ``graded_at`` в поясе ученика."""

    week_start: date  # понедельник недели в поясе ученика
    average_percent: int
    graded_count: int


class OnTimeStats(BaseModel):
    """«Сдано в срок»: ``on_time`` из ``submitted_at <= original_due_at`` (docs/04 §5.3)."""

    on_time_count: int
    total_count: int
    percent: int | None  # ``None``, если сданных/сгоревших выдач за период нет


class MockExamPoint(BaseModel):
    """Точка серии пробников: оценка/тестовый балл или процент для нестандартного максимума."""

    exam_date: date
    exam_type_code: str
    exam_type_name: str
    result_kind: ExamResultKind
    primary_score: int
    max_primary: int
    converted_value: int | None
    scale_applicable: bool
    percent: int  # primary_score * 100 / max_primary (docs/04 §11)


class AttendanceStats(BaseModel):
    """Посещаемость за период: число отметок по статусам участия."""

    attended: int
    no_show: int
    cancelled: int
    pending: int


class StudentReport(BaseModel):
    """Отчёт ученика за период (``from`` включительно, ``to`` исключительно)."""

    student_id: int
    timezone: str
    homework_weekly: list[WeeklyHomeworkPoint]
    homework_last_percent: int | None  # процент последней проверенной работы периода
    on_time: OnTimeStats
    mock_exams: list[MockExamPoint]
    attendance: AttendanceStats
