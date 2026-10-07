"""Роутер ``/student/lessons*`` (docs/08 §4): уроки самого ученика.

Только свои уроки: чужой урок — 404. В ответе нет заметок преподавателя, цен и данных других
участников (только их число); это проверяет тест приватности ``test_privacy_contract``.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from src.api.deps import StudentActor, get_schedule_service
from src.api.v1.responses import error_responses
from src.schemas.schedule import StudentLessonItem
from src.services.schedule import ScheduleService

router = APIRouter(prefix="/student/lessons", tags=["student-lessons"])

Service = Annotated[ScheduleService, Depends(get_schedule_service)]


@router.get(
    "",
    response_model=list[StudentLessonItem],
    summary="Мои уроки за период",
    operation_id="list_student_lessons",
    responses=error_responses(401, 403, 422, 429),
)
async def list_student_lessons(
    actor: StudentActor,
    service: Service,
    start: Annotated[datetime, Query(alias="from")],
    end: Annotated[datetime, Query(alias="to")],
) -> list[StudentLessonItem]:
    """Уроки ученика с началом в ``[from, to)``; период не больше года."""
    return await service.list_student_lessons(actor, start=start, end=end)


@router.get(
    "/{lesson_id}",
    response_model=StudentLessonItem,
    summary="Карточка урока",
    operation_id="get_student_lesson",
    responses=error_responses(401, 403, 404, 429),
)
async def get_student_lesson(
    lesson_id: Annotated[int, Path(ge=1)], actor: StudentActor, service: Service
) -> StudentLessonItem:
    """Карточка: ссылки Телемоста и доски (урок → профиль), число участников."""
    return await service.get_student_lesson(actor, lesson_id)
