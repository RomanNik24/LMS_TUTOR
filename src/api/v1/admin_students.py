"""Роутер ``/admin/students*`` (docs/08 §5.2): профили учеников для owner и manager.

Роутер тонкий: разбор запроса → вызов ``StudentService`` → ответ. Права по ролям проверяют
зависимость ``StaffActor`` и сервис; менеджер получает карточку без цены (``StudentCardManager``),
владелец — с ценой (``StudentCardOwner``).
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response, status

from src.api.deps import StaffActor, get_bot_username, get_stats_service, get_student_service
from src.api.v1.invitations import invitation_response
from src.api.v1.responses import error_responses
from src.core.constants import LIST_LIMIT_DEFAULT, LIST_LIMIT_MAX
from src.schemas.reports import StudentReport
from src.schemas.students import (
    InvitationResponse,
    StudentCardResponse,
    StudentCreate,
    StudentListPage,
    StudentUpdate,
)
from src.services.stats import StatsService
from src.services.students import StudentService, StudentStatus

router = APIRouter(prefix="/admin/students", tags=["admin-students"])

StudentId = Annotated[int, Path(ge=1)]
Service = Annotated[StudentService, Depends(get_student_service)]


@router.get(
    "",
    response_model=StudentListPage,
    summary="Список учеников",
    operation_id="list_students",
    responses=error_responses(401, 403, 422, 429),
)
async def list_students(
    actor: StaffActor,
    service: Service,
    status_filter: Annotated[StudentStatus, Query(alias="status")] = StudentStatus.ACTIVE,
    q: Annotated[str | None, Query(max_length=150)] = None,
    limit: Annotated[int, Query(ge=1, le=LIST_LIMIT_MAX)] = LIST_LIMIT_DEFAULT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> StudentListPage:
    """Список учеников: ``status=active|archived``, поиск ``q`` по имени, пагинация."""
    return await service.list_students(actor, status=status_filter, q=q, limit=limit, offset=offset)


@router.post(
    "",
    response_model=StudentCardResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создать профиль ученика",
    operation_id="create_student",
    responses=error_responses(400, 401, 403, 422, 429),
)
async def create_student(
    body: StudentCreate, actor: StaffActor, service: Service
) -> StudentCardResponse:
    """Создать профиль; цену может задать только владелец (иначе 403)."""
    return await service.create_student(actor, body)


@router.get(
    "/{student_id}",
    response_model=StudentCardResponse,
    summary="Карточка ученика",
    operation_id="get_student",
    responses=error_responses(401, 403, 404, 429),
)
async def get_student(
    student_id: StudentId, actor: StaffActor, service: Service
) -> StudentCardResponse:
    """Карточка: цена (``lesson_price``) есть только в ответе владельцу."""
    return await service.get_student_card_for_staff(actor, student_id)


@router.patch(
    "/{student_id}",
    response_model=StudentCardResponse,
    summary="Изменить профиль ученика",
    operation_id="update_student",
    responses=error_responses(400, 401, 403, 404, 422, 429),
)
async def update_student(
    student_id: StudentId, body: StudentUpdate, actor: StaffActor, service: Service
) -> StudentCardResponse:
    """Частичная правка; цену меняет только владелец, изменение пишется в ``audit_log``."""
    return await service.update_student(actor, student_id, body)


@router.post(
    "/{student_id}/archive",
    response_model=StudentCardResponse,
    summary="Архивировать ученика",
    operation_id="archive_student",
    responses=error_responses(400, 401, 403, 404, 429),
)
async def archive_student(
    student_id: StudentId, actor: StaffActor, service: Service
) -> StudentCardResponse:
    """Архив: вход закрыт, сессии удалены, данные остаются."""
    return await service.archive_student(actor, student_id)


@router.post(
    "/{student_id}/restore",
    response_model=StudentCardResponse,
    summary="Вернуть ученика из архива",
    operation_id="restore_student",
    responses=error_responses(400, 401, 403, 404, 429),
)
async def restore_student(
    student_id: StudentId, actor: StaffActor, service: Service
) -> StudentCardResponse:
    """Вернуть из архива."""
    return await service.restore_student(actor, student_id)


@router.post(
    "/{student_id}/invitations",
    response_model=InvitationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создать или перевыпустить приглашение ученика",
    operation_id="create_student_invitation",
    responses=error_responses(400, 401, 403, 404, 429),
)
async def create_student_invitation(
    student_id: StudentId,
    actor: StaffActor,
    service: Service,
    bot_username: Annotated[str, Depends(get_bot_username)],
) -> InvitationResponse:
    """Выпустить приглашение (прежние отзываются); токен виден только в этом ответе."""
    issued = await service.invite_student(actor, student_id)
    return invitation_response(issued, bot_username)


@router.post(
    "/{student_id}/unlink-telegram",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Снять привязку Telegram",
    operation_id="unlink_student_telegram",
    responses=error_responses(400, 401, 403, 404, 429),
)
async def unlink_student_telegram(
    student_id: StudentId, actor: StaffActor, service: Service
) -> Response:
    """Снять привязку Telegram: сессии удаляются, запись в ``audit_log``."""
    await service.unlink_telegram(actor, student_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{student_id}/report",
    response_model=StudentReport,
    summary="Отчёт по ученику",
    operation_id="get_admin_student_report",
    responses=error_responses(400, 401, 403, 404, 422, 429),
)
async def get_admin_student_report(
    student_id: Annotated[int, Path(ge=1)],
    actor: StaffActor,
    service: Annotated[StatsService, Depends(get_stats_service)],
    start: Annotated[datetime, Query(alias="from")],
    end: Annotated[datetime, Query(alias="to")],
) -> StudentReport:
    """ДЗ, пробники и посещаемость ученика за ``[from, to)``; без финансов."""
    return await service.student_report(actor, student_id, start, end)
