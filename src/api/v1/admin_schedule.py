"""Роутер расписания для персонала: ``/admin/lessons*`` и ``/admin/schedule-templates*``.

Роутер тонкий: разбор запроса → вызов ``ScheduleService`` → ответ (docs/08 §5.4). Права —
``StaffActor`` (owner и manager); в ответах нет финансовых полей, поэтому менеджер видит то же,
что владелец.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status

from src.api.deps import StaffActor, get_schedule_service
from src.api.v1.responses import error_responses
from src.core.constants import LIST_LIMIT_DEFAULT, LIST_LIMIT_MAX
from src.core.enums import LessonStatus
from src.schemas.schedule import (
    HORIZON_WEEKS_MAX,
    GenerationResult,
    LessonCancel,
    LessonComplete,
    LessonCreate,
    LessonItem,
    LessonListPage,
    LessonReschedule,
    LessonUpdate,
    TemplateCreate,
    TemplateItem,
    TemplateUpdate,
)
from src.services.schedule import ScheduleService

router = APIRouter(prefix="/admin", tags=["admin-schedule"])

LessonId = Annotated[int, Path(ge=1)]
TemplateId = Annotated[int, Path(ge=1)]
Service = Annotated[ScheduleService, Depends(get_schedule_service)]


# ---------------------------------------------------------------- уроки


@router.get(
    "/lessons",
    response_model=LessonListPage,
    summary="Список уроков",
    operation_id="list_lessons",
    responses=error_responses(401, 403, 422, 429),
)
async def list_lessons(
    actor: StaffActor,
    service: Service,
    start: Annotated[datetime, Query(alias="from")],
    end: Annotated[datetime, Query(alias="to")],
    student_id: Annotated[int | None, Query(ge=1)] = None,
    teacher_id: Annotated[int | None, Query(ge=1)] = None,
    status_filter: Annotated[LessonStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=LIST_LIMIT_MAX)] = LIST_LIMIT_DEFAULT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> LessonListPage:
    """Уроки с началом в ``[from, to)``; период не больше года."""
    return await service.list_lessons(
        actor,
        start=start,
        end=end,
        student_id=student_id,
        teacher_id=teacher_id,
        status=status_filter,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/lessons",
    response_model=LessonItem,
    status_code=status.HTTP_201_CREATED,
    summary="Создать урок",
    operation_id="create_lesson",
    responses=error_responses(400, 401, 403, 404, 409, 422, 429),
)
async def create_lesson(body: LessonCreate, actor: StaffActor, service: Service) -> LessonItem:
    """Создать разовый урок; пересечение с другим уроком преподавателя — 409 ``lesson_overlap``."""
    return await service.create_lesson(actor, body)


@router.get(
    "/lessons/{lesson_id}",
    response_model=LessonItem,
    summary="Детали урока",
    operation_id="get_lesson",
    responses=error_responses(401, 403, 404, 429),
)
async def get_lesson(lesson_id: LessonId, actor: StaffActor, service: Service) -> LessonItem:
    """Урок с участниками и посещаемостью."""
    return await service.get_lesson(actor, lesson_id)


@router.patch(
    "/lessons/{lesson_id}",
    response_model=LessonItem,
    summary="Изменить урок",
    operation_id="update_lesson",
    responses=error_responses(400, 401, 403, 404, 422, 429),
)
async def update_lesson(
    lesson_id: LessonId, body: LessonUpdate, actor: StaffActor, service: Service
) -> LessonItem:
    """Тема, заметка, ссылки, участники; урок из шаблона становится «изменённым вручную»."""
    return await service.update_lesson(actor, lesson_id, body)


@router.post(
    "/lessons/{lesson_id}/reschedule",
    response_model=LessonItem,
    summary="Перенести урок",
    operation_id="reschedule_lesson",
    responses=error_responses(400, 401, 403, 404, 409, 422, 429),
)
async def reschedule_lesson(
    lesson_id: LessonId, body: LessonReschedule, actor: StaffActor, service: Service
) -> LessonItem:
    """Новое время; пересечение — 409 ``lesson_overlap``."""
    return await service.reschedule_lesson(actor, lesson_id, body)


@router.post(
    "/lessons/{lesson_id}/cancel",
    response_model=LessonItem,
    summary="Отменить урок",
    operation_id="cancel_lesson",
    responses=error_responses(400, 401, 403, 404, 422, 429),
)
async def cancel_lesson(
    lesson_id: LessonId, body: LessonCancel, actor: StaffActor, service: Service
) -> LessonItem:
    """Отмена с причиной; за учеников из ``billable_student_ids`` отмена засчитывается."""
    return await service.cancel_lesson(actor, lesson_id, body)


@router.post(
    "/lessons/{lesson_id}/complete",
    response_model=LessonItem,
    summary="Отметить проведение урока",
    operation_id="complete_lesson",
    responses=error_responses(400, 401, 403, 404, 422, 429),
)
async def complete_lesson(
    lesson_id: LessonId, body: LessonComplete, actor: StaffActor, service: Service
) -> LessonItem:
    """Посещаемость каждого участника; цена фиксируется сервером в момент отметки."""
    return await service.complete_lesson(actor, lesson_id, body)


# ---------------------------------------------------------------- шаблоны


@router.get(
    "/schedule-templates",
    response_model=list[TemplateItem],
    summary="Шаблоны расписания",
    operation_id="list_schedule_templates",
    responses=error_responses(401, 403, 429),
)
async def list_schedule_templates(actor: StaffActor, service: Service) -> list[TemplateItem]:
    """Все шаблоны, включая отключённые."""
    return await service.list_templates(actor)


@router.post(
    "/schedule-templates",
    response_model=TemplateItem,
    status_code=status.HTTP_201_CREATED,
    summary="Создать шаблон расписания",
    operation_id="create_schedule_template",
    responses=error_responses(400, 401, 403, 404, 422, 429),
)
async def create_schedule_template(
    body: TemplateCreate, actor: StaffActor, service: Service
) -> TemplateItem:
    """Шаблон «каждую неделю»; уроки на горизонт создаются сразу."""
    return await service.create_template(actor, body)


@router.post(
    "/schedule-templates/generate",
    response_model=GenerationResult,
    summary="Дозаполнить уроки по шаблонам",
    operation_id="generate_lessons",
    responses=error_responses(401, 403, 422, 429),
)
async def generate_lessons(
    actor: StaffActor,
    service: Service,
    horizon_weeks: Annotated[int | None, Query(ge=1, le=HORIZON_WEEKS_MAX)] = None,
) -> GenerationResult:
    """Принудительная идемпотентная генерация на горизонт (по умолчанию из настроек)."""
    return await service.generate_lessons(actor, horizon_weeks)


@router.patch(
    "/schedule-templates/{template_id}",
    response_model=TemplateItem,
    summary="Изменить шаблон расписания",
    operation_id="update_schedule_template",
    responses=error_responses(400, 401, 403, 404, 422, 429),
)
async def update_schedule_template(
    template_id: TemplateId, body: TemplateUpdate, actor: StaffActor, service: Service
) -> TemplateItem:
    """Правка затрагивает только будущие неизменённые уроки шаблона."""
    return await service.update_template(actor, template_id, body)


@router.post(
    "/schedule-templates/{template_id}/deactivate",
    response_model=TemplateItem,
    summary="Отключить шаблон расписания",
    operation_id="deactivate_schedule_template",
    responses=error_responses(401, 403, 404, 429),
)
async def deactivate_schedule_template(
    template_id: TemplateId, actor: StaffActor, service: Service
) -> TemplateItem:
    """Пауза: новые уроки не создаются, будущие неизменённые удаляются."""
    return await service.deactivate_template(actor, template_id)
