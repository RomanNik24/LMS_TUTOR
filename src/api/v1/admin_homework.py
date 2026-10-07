"""Роутер ``/admin/homework*`` и ``/admin/assignments*`` (docs/08 §5.5): ДЗ для персонала.

Права — ``StaffActor`` (owner и manager); в ответах нет финансовых полей.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Path, Query, UploadFile, status

from src.api.deps import (
    StaffActor,
    get_assignment_query_service,
    get_extension_service,
    get_file_service,
    get_grading_service,
    get_homework_service,
    read_upload,
    upload_rate_limit,
)
from src.api.v1.responses import error_responses
from src.core.constants import LIST_LIMIT_DEFAULT, LIST_LIMIT_MAX
from src.core.enums import AssignmentStatus
from src.schemas.files import HomeworkFileItem, MaterialItem
from src.schemas.homework import (
    AssigneesAdd,
    ExtendRequest,
    ExtensionItem,
    GradeItem,
    GradeRequest,
    HomeworkCreate,
    HomeworkItem,
    HomeworkListPage,
    ReturnRequest,
)
from src.schemas.homework_views import AdminAssignmentDetail, AdminAssignmentPage
from src.services.assignments import AssignmentQueryService
from src.services.extensions import ExtensionService
from src.services.files import FileService
from src.services.grading import GradingService
from src.services.homework import HomeworkService

router = APIRouter(prefix="/admin", tags=["admin-homework"])

HomeworkId = Annotated[int, Path(ge=1)]
AssignmentId = Annotated[int, Path(ge=1)]
Homeworks = Annotated[HomeworkService, Depends(get_homework_service)]
Queries = Annotated[AssignmentQueryService, Depends(get_assignment_query_service)]
Grading = Annotated[GradingService, Depends(get_grading_service)]
Extensions = Annotated[ExtensionService, Depends(get_extension_service)]
Files = Annotated[FileService, Depends(get_file_service)]
Limit = Annotated[int, Query(ge=1, le=LIST_LIMIT_MAX)]
Offset = Annotated[int, Query(ge=0)]


@router.get(
    "/homework",
    response_model=HomeworkListPage,
    summary="Список заданий",
    operation_id="list_homework",
    responses=error_responses(401, 403, 422, 429),
)
async def list_homework(
    actor: StaffActor,
    service: Homeworks,
    limit: Limit = LIST_LIMIT_DEFAULT,
    offset: Offset = 0,
) -> HomeworkListPage:
    """Задания, новые сверху, со счётчиками «сдали N из M»."""
    return await service.list_homeworks(actor, limit=limit, offset=offset)


@router.post(
    "/homework",
    response_model=HomeworkItem,
    status_code=status.HTTP_201_CREATED,
    summary="Создать задание и выдать",
    operation_id="create_homework",
    responses=error_responses(400, 401, 403, 404, 422, 429),
)
async def create_homework(
    body: HomeworkCreate, actor: StaffActor, service: Homeworks
) -> HomeworkItem:
    """Создать задание и выдать его ученикам."""
    return await service.create_homework(actor, body)


@router.get(
    "/homework/{homework_id}",
    response_model=HomeworkItem,
    summary="Задание и его выдачи",
    operation_id="get_homework",
    responses=error_responses(401, 403, 404, 429),
)
async def get_homework(
    homework_id: HomeworkId, actor: StaffActor, service: Homeworks
) -> HomeworkItem:
    """Задание со всеми выдачами и материалами."""
    return await service.get_homework(actor, homework_id)


@router.post(
    "/homework/{homework_id}/assignees",
    response_model=HomeworkItem,
    summary="Добавить учеников к заданию",
    operation_id="add_homework_assignees",
    responses=error_responses(400, 401, 403, 404, 422, 429),
)
async def add_homework_assignees(
    homework_id: HomeworkId, body: AssigneesAdd, actor: StaffActor, service: Homeworks
) -> HomeworkItem:
    """Выдать задание ещё ученикам; уже получившие пропускаются."""
    return await service.add_assignees(actor, homework_id, body)


@router.post(
    "/homework/{homework_id}/materials",
    response_model=MaterialItem,
    status_code=status.HTTP_201_CREATED,
    summary="Загрузить материал к заданию",
    operation_id="upload_homework_material",
    dependencies=[Depends(upload_rate_limit)],
    responses=error_responses(400, 401, 403, 404, 413, 415, 422, 429),
)
async def upload_homework_material(
    homework_id: HomeworkId,
    actor: StaffActor,
    service: Files,
    file: Annotated[UploadFile, File()],
) -> MaterialItem:
    """Файл-материал (multipart, поле ``file``)."""
    name, data = await read_upload(file)
    return await service.upload_material(actor, homework_id, name, data)


@router.get(
    "/assignments",
    response_model=AdminAssignmentPage,
    summary="Выдачи с фильтрами",
    operation_id="list_assignments",
    responses=error_responses(401, 403, 422, 429),
)
async def list_assignments(
    actor: StaffActor,
    service: Queries,
    status_filter: Annotated[AssignmentStatus | None, Query(alias="status")] = None,
    student_id: Annotated[int | None, Query(ge=1)] = None,
    overdue: bool = False,
    limit: Limit = LIST_LIMIT_DEFAULT,
    offset: Offset = 0,
) -> AdminAssignmentPage:
    """Выдачи по статусу, ученику и признаку «просрочено»."""
    return await service.list_staff(
        actor,
        status=status_filter,
        student_id=student_id,
        overdue=overdue,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/assignments/review-queue",
    response_model=AdminAssignmentPage,
    summary="Очередь проверки",
    operation_id="list_review_queue",
    responses=error_responses(401, 403, 422, 429),
)
async def list_review_queue(
    actor: StaffActor,
    service: Queries,
    limit: Limit = LIST_LIMIT_DEFAULT,
    offset: Offset = 0,
) -> AdminAssignmentPage:
    """Сданные работы, самые давние первыми."""
    return await service.review_queue(actor, limit=limit, offset=offset)


@router.get(
    "/assignments/{assignment_id}",
    response_model=AdminAssignmentDetail,
    summary="Выдача: файлы и журнал переносов",
    operation_id="get_assignment",
    responses=error_responses(401, 403, 404, 429),
)
async def get_assignment(
    assignment_id: AssignmentId, actor: StaffActor, service: Queries
) -> AdminAssignmentDetail:
    """Карточка выдачи для персонала."""
    return await service.get_staff(actor, assignment_id)


@router.post(
    "/assignments/{assignment_id}/grade",
    response_model=GradeItem,
    summary="Поставить оценку",
    operation_id="grade_assignment",
    responses=error_responses(400, 401, 403, 404, 422, 429),
)
async def grade_assignment(
    assignment_id: AssignmentId, body: GradeRequest, actor: StaffActor, service: Grading
) -> GradeItem:
    """Оценка 0..max_score; для пробника создаёт результат."""
    return await service.grade_assignment(actor, assignment_id, body)


@router.post(
    "/assignments/{assignment_id}/return",
    response_model=GradeItem,
    summary="Вернуть на доработку",
    operation_id="return_assignment",
    responses=error_responses(400, 401, 403, 404, 422, 429),
)
async def return_assignment(
    assignment_id: AssignmentId, body: ReturnRequest, actor: StaffActor, service: Grading
) -> GradeItem:
    """Вернуть работу с комментарием и новым сроком."""
    return await service.return_for_revision(actor, assignment_id, body)


@router.post(
    "/assignments/{assignment_id}/extend",
    response_model=ExtensionItem,
    summary="Перенести дедлайн",
    operation_id="extend_assignment",
    responses=error_responses(400, 401, 403, 404, 422, 429),
)
async def extend_assignment(
    assignment_id: AssignmentId,
    actor: StaffActor,
    service: Extensions,
    body: ExtendRequest | None = None,
) -> ExtensionItem:
    """Без тела — на ближайшее занятие; ``due_at`` — вручную. Не больше двух переносов."""
    return await service.extend_deadline(actor, assignment_id, body or ExtendRequest())


@router.post(
    "/assignments/{assignment_id}/review-files",
    response_model=HomeworkFileItem,
    status_code=status.HTTP_201_CREATED,
    summary="Файл преподавателя к проверке",
    operation_id="upload_review_file",
    dependencies=[Depends(upload_rate_limit)],
    responses=error_responses(400, 401, 403, 404, 413, 415, 422, 429),
)
async def upload_review_file(
    assignment_id: AssignmentId,
    actor: StaffActor,
    service: Files,
    file: Annotated[UploadFile, File()],
) -> HomeworkFileItem:
    """Файл проверки (multipart, поле ``file``)."""
    name, data = await read_upload(file)
    return await service.upload_review(actor, assignment_id, name, data)
