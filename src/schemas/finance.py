"""Схемы финансов, статистики отмен и журнала аудита (T7.02, docs/08 §5.8).

Финансовые схемы (``Earnings*``) — только для владельца; ``Cancellation*`` денег не содержат и
доступны всему персоналу.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel

from src.core.enums import UserRole
from src.schemas.roles import audience_config


class EarningsGroupBy(StrEnum):
    """Разрез отчёта «Заработано / ожидается»."""

    STUDENT = "student"
    SUBJECT = "subject"
    WEEK = "week"
    MONTH = "month"


class EarningsRow(BaseModel):
    """Строка разреза: ключ, подпись и суммы (рубли)."""

    model_config = audience_config(UserRole.OWNER)

    key: str  # id ученика, код предмета или дата начала недели/месяца (YYYY-MM-DD)
    label: str
    earned: int
    earned_lessons: int  # сколько оплачиваемых участий вошло в «заработано»
    expected: int
    planned_lessons: int  # сколько участий в запланированных уроках вошло в «ожидается»


class EarningsReport(BaseModel):
    """Заработано и ожидается за период с разрезом."""

    model_config = audience_config(UserRole.OWNER)

    period_start: datetime
    period_end: datetime
    group_by: EarningsGroupBy
    timezone: str
    earned_total: int
    expected_total: int
    rows: list[EarningsRow]


class CancellationStudentRow(BaseModel):
    """Сколько отменённых занятий у ученика за период."""

    student_id: int
    student_name: str
    cancelled_lessons: int


class CancellationStats(BaseModel):
    """Статистика отмен за период: уроки ``cancelled`` по дате начала (docs/04 §11)."""

    period_start: datetime
    period_end: datetime
    cancelled_lessons: int
    cancelled_participations: int
    by_student: list[CancellationStudentRow]


class AuditItem(BaseModel):
    """Запись журнала аудита."""

    model_config = audience_config(UserRole.OWNER)

    id: int
    actor_user_id: int | None
    actor_name: str | None
    action: str
    entity_type: str
    entity_id: int | None
    data: dict[str, object]
    created_at: datetime


class AuditPage(BaseModel):
    """Страница журнала аудита (новые первыми)."""

    model_config = audience_config(UserRole.OWNER)

    items: list[AuditItem]
    total: int
    limit: int
    offset: int
