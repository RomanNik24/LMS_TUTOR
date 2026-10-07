"""Схемы расписания и уроков (docs/08 §5.4, T3.04). Тела запросов и ответ для сотрудников."""

from datetime import date, datetime, time
from typing import Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from src.core import texts
from src.core.constants import DEFAULT_USER_TIMEZONE
from src.core.enums import AttendanceStatus, LessonStatus
from src.schemas.validators import https_url, iana_timezone

LESSON_MAX_MINUTES = 12 * 60
LESSON_MAX_PARTICIPANTS = 20
TOPIC_MAX_LENGTH = 255
URL_MAX_LENGTH = 500
CANCEL_REASON_MAX_LENGTH = 255
WEEKDAY_MIN = 1
WEEKDAY_MAX = 7
DEFAULT_DURATION_MINUTES = 60
HORIZON_WEEKS_MAX = 52


def _check_time_range(start_at: datetime, end_at: datetime) -> None:
    """Общая проверка интервала урока: конец позже начала, не длиннее 12 часов."""
    if end_at <= start_at:
        raise ValueError(texts.LESSON_END_BEFORE_START)
    if (end_at - start_at).total_seconds() > LESSON_MAX_MINUTES * 60:
        raise ValueError(texts.LESSON_TOO_LONG)


class LessonCreate(BaseModel):
    """Создание разового урока: предмет, участники, время, ссылки и тема."""

    model_config = ConfigDict(extra="forbid")

    subject_code: str = Field(min_length=1, max_length=32)
    student_ids: list[int] = Field(min_length=1, max_length=LESSON_MAX_PARTICIPANTS)
    start_at: AwareDatetime
    end_at: AwareDatetime
    teacher_id: int | None = None
    video_url_override: str | None = Field(default=None, max_length=URL_MAX_LENGTH)
    board_url_override: str | None = Field(default=None, max_length=URL_MAX_LENGTH)
    topic: str | None = Field(default=None, max_length=TOPIC_MAX_LENGTH)

    _urls = field_validator("video_url_override", "board_url_override")(https_url)

    @field_validator("topic")
    @classmethod
    def _topic(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @model_validator(mode="after")
    def _check(self) -> Self:
        _check_time_range(self.start_at, self.end_at)
        if len(set(self.student_ids)) != len(self.student_ids):
            raise ValueError(texts.LESSON_STUDENTS_DUPLICATE)
        return self


class LessonReschedule(BaseModel):
    """Перенос урока на новое время."""

    model_config = ConfigDict(extra="forbid")

    start_at: AwareDatetime
    end_at: AwareDatetime

    @model_validator(mode="after")
    def _check(self) -> Self:
        _check_time_range(self.start_at, self.end_at)
        return self


class LessonCancel(BaseModel):
    """Отмена урока: причина и ученики, за которых отмена засчитывается как оплачиваемая."""

    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=CANCEL_REASON_MAX_LENGTH)
    billable_student_ids: list[int] = Field(
        default_factory=list, max_length=LESSON_MAX_PARTICIPANTS
    )

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @model_validator(mode="after")
    def _check(self) -> Self:
        if len(set(self.billable_student_ids)) != len(self.billable_student_ids):
            raise ValueError(texts.LESSON_STUDENTS_DUPLICATE)
        return self


class LessonMark(BaseModel):
    """Отметка одного участника: «был», «не пришёл» или «отменено» и признак «засчитать»."""

    model_config = ConfigDict(extra="forbid")

    student_id: int
    attendance: Literal[
        AttendanceStatus.ATTENDED, AttendanceStatus.NO_SHOW, AttendanceStatus.CANCELLED
    ]
    is_billable: bool | None = None


class LessonComplete(BaseModel):
    """Отметка проведения: по записи на каждого участника урока."""

    model_config = ConfigDict(extra="forbid")

    marks: list[LessonMark] = Field(min_length=1, max_length=LESSON_MAX_PARTICIPANTS)

    @model_validator(mode="after")
    def _check(self) -> Self:
        ids = [mark.student_id for mark in self.marks]
        if len(set(ids)) != len(ids):
            raise ValueError(texts.LESSON_STUDENTS_DUPLICATE)
        return self


class LessonParticipantItem(BaseModel):
    """Участник урока в ответе для сотрудников (без цены и признака оплаты)."""

    student_id: int
    display_name: str
    attendance: AttendanceStatus


class LessonItem(BaseModel):
    """Урок в ответе для сотрудников. Финансовых полей нет: их добавит схема владельца."""

    id: int
    teacher_id: int
    subject_code: str
    start_at: datetime
    end_at: datetime
    status: LessonStatus
    is_detached: bool
    video_url_override: str | None
    board_url_override: str | None
    topic: str | None
    completed_at: datetime | None
    cancelled_at: datetime | None
    cancel_reason: str | None
    participants: list[LessonParticipantItem]


# ---------------------------------------------------------------- шаблоны (T3.06)


class TemplateCreate(BaseModel):
    """Создание шаблона «каждую неделю»: день, локальное время, пояс, участники, период."""

    model_config = ConfigDict(extra="forbid")

    subject_code: str = Field(min_length=1, max_length=32)
    student_ids: list[int] = Field(min_length=1, max_length=LESSON_MAX_PARTICIPANTS)
    weekday: int = Field(ge=WEEKDAY_MIN, le=WEEKDAY_MAX)
    start_local_time: time
    duration_minutes: int = Field(default=DEFAULT_DURATION_MINUTES, ge=1, le=LESSON_MAX_MINUTES)
    timezone: str = DEFAULT_USER_TIMEZONE
    starts_on: date
    ends_on: date | None = None
    teacher_id: int | None = None

    _tz = field_validator("timezone")(iana_timezone)

    @field_validator("start_local_time")
    @classmethod
    def _naive_time(cls, value: time) -> time:
        # Время задаётся «на часах» в поясе шаблона: смещение внутри значения недопустимо.
        if value.tzinfo is not None:
            raise ValueError(texts.TEMPLATE_TIME_HAS_TZ)
        return value

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.ends_on is not None and self.ends_on < self.starts_on:
            raise ValueError(texts.TEMPLATE_ENDS_BEFORE_START)
        if len(set(self.student_ids)) != len(self.student_ids):
            raise ValueError(texts.LESSON_STUDENTS_DUPLICATE)
        return self


class TemplateUpdate(BaseModel):
    """Частичное изменение шаблона: применяются только переданные поля.

    ``ends_on = null`` снимает дату окончания; остальные поля очищать нельзя.
    """

    model_config = ConfigDict(extra="forbid")

    student_ids: list[int] | None = Field(
        default=None, min_length=1, max_length=LESSON_MAX_PARTICIPANTS
    )
    weekday: int | None = Field(default=None, ge=WEEKDAY_MIN, le=WEEKDAY_MAX)
    start_local_time: time | None = None
    duration_minutes: int | None = Field(default=None, ge=1, le=LESSON_MAX_MINUTES)
    timezone: str | None = None
    starts_on: date | None = None
    ends_on: date | None = None
    is_active: bool | None = None

    @field_validator("timezone")
    @classmethod
    def _tz(cls, value: str | None) -> str | None:
        return None if value is None else iana_timezone(value)

    @field_validator("start_local_time")
    @classmethod
    def _naive_time(cls, value: time | None) -> time | None:
        if value is not None and value.tzinfo is not None:
            raise ValueError(texts.TEMPLATE_TIME_HAS_TZ)
        return value

    @model_validator(mode="after")
    def _check(self) -> Self:
        if not self.model_fields_set:
            raise ValueError(texts.TEMPLATE_UPDATE_EMPTY)
        for name in (
            "student_ids",
            "weekday",
            "start_local_time",
            "duration_minutes",
            "timezone",
            "starts_on",
            "is_active",
        ):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name}: {texts.TEMPLATE_FIELD_NOT_NULLABLE}")
        if len(self.student_ids or []) != len(set(self.student_ids or [])):
            raise ValueError(texts.LESSON_STUDENTS_DUPLICATE)
        return self


class TemplateItem(BaseModel):
    """Шаблон расписания в ответе для сотрудников."""

    id: int
    teacher_id: int
    subject_code: str
    student_ids: list[int]
    weekday: int
    start_local_time: time
    duration_minutes: int
    timezone: str
    starts_on: date
    ends_on: date | None
    is_active: bool
    generated_until: date | None


class GenerationResult(BaseModel):
    """Итог генерации уроков: сколько создано и сколько пропущено (дубль или пересечение)."""

    templates: int
    created: int
    skipped: int
