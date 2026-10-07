"""Роутер ``/student/homework*`` (docs/08 §4): ДЗ самого ученика.

Только свои выдачи: чужая — 404. Журнала переносов в ответах нет, только ``extensions_left``;
заметок преподавателя и денег тоже нет (проверяет ``test_privacy_contract``).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Path, Query, Response, UploadFile, status

from src.api.deps import (
    StudentActor,
    get_assignment_query_service,
    get_file_service,
    get_submission_service,
    read_upload,
    upload_rate_limit,
)
from src.api.v1.responses import error_responses
from src.core.constants import LIST_LIMIT_DEFAULT, LIST_LIMIT_MAX
from src.schemas.files import HomeworkFileItem
from src.schemas.homework import SubmissionItem, SubmitRequest
from src.schemas.homework_views import (
    StudentAssignmentDetail,
    StudentAssignmentPage,
    StudentHomeworkFilter,
)
from src.services.assignments import AssignmentQueryService
from src.services.files import FileService
from src.services.submissions import SubmissionService

router = APIRouter(prefix="/student/homework", tags=["student-homework"])

AssignmentId = Annotated[int, Path(ge=1)]
Queries = Annotated[AssignmentQueryService, Depends(get_assignment_query_service)]
Files = Annotated[FileService, Depends(get_file_service)]
Submissions = Annotated[SubmissionService, Depends(get_submission_service)]


@router.get(
    "",
    response_model=StudentAssignmentPage,
    summary="Мои домашние задания",
    operation_id="list_student_homework",
    responses=error_responses(401, 403, 422, 429),
)
async def list_student_homework(
    actor: StudentActor,
    service: Queries,
    status_filter: Annotated[StudentHomeworkFilter | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=LIST_LIMIT_MAX)] = LIST_LIMIT_DEFAULT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> StudentAssignmentPage:
    """Свои выдачи по сроку; ``status``: active, submitted, graded, expired."""
    return await service.list_student(actor, status_filter, limit=limit, offset=offset)


@router.get(
    "/{assignment_id}",
    response_model=StudentAssignmentDetail,
    summary="Карточка домашнего задания",
    operation_id="get_student_homework",
    responses=error_responses(401, 403, 404, 429),
)
async def get_student_homework(
    assignment_id: AssignmentId, actor: StudentActor, service: Queries
) -> StudentAssignmentDetail:
    """Описание, материалы, дедлайн, ``is_overdue``, ``extensions_left``, оценка, свои файлы."""
    return await service.get_student(actor, assignment_id)


@router.post(
    "/{assignment_id}/files",
    response_model=HomeworkFileItem,
    status_code=status.HTTP_201_CREATED,
    summary="Загрузить файл решения",
    operation_id="upload_solution_file",
    dependencies=[Depends(upload_rate_limit)],
    responses=error_responses(400, 401, 403, 404, 413, 415, 422, 429),
)
async def upload_solution_file(
    assignment_id: AssignmentId,
    actor: StudentActor,
    service: Files,
    file: Annotated[UploadFile, File()],
) -> HomeworkFileItem:
    """Один файл решения (multipart, поле ``file``): jpg/png/heic/pdf, до 10 МБ, до 10 штук."""
    name, data = await read_upload(file)
    return await service.upload_solution(actor, assignment_id, name, data)


@router.delete(
    "/{assignment_id}/files/{file_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить свой файл решения",
    operation_id="delete_solution_file",
    responses=error_responses(400, 401, 403, 404, 429),
)
async def delete_solution_file(
    assignment_id: AssignmentId,
    file_id: Annotated[int, Path(ge=1)],
    actor: StudentActor,
    service: Files,
) -> Response:
    """Удалить файл, пока работа не сдана на проверку."""
    await service.delete_solution(actor, assignment_id, file_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{assignment_id}/submit",
    response_model=SubmissionItem,
    summary="Сдать работу с файлами",
    operation_id="submit_homework",
    responses=error_responses(400, 401, 403, 404, 422, 429),
)
async def submit_homework(
    assignment_id: AssignmentId,
    actor: StudentActor,
    service: Submissions,
    body: SubmitRequest | None = None,
) -> SubmissionItem:
    """Сдача; нужен хотя бы один загруженный файл."""
    return await service.submit_files(actor, assignment_id, body or SubmitRequest())


@router.post(
    "/{assignment_id}/self-report",
    response_model=SubmissionItem,
    summary="Отметить «Сделал» без файлов",
    operation_id="self_report_homework",
    responses=error_responses(400, 401, 403, 404, 422, 429),
)
async def self_report_homework(
    assignment_id: AssignmentId,
    actor: StudentActor,
    service: Submissions,
    body: SubmitRequest | None = None,
) -> SubmissionItem:
    """Сдача кнопкой «Сделал»: файлы не обязательны."""
    return await service.submit_self_reported(actor, assignment_id, body or SubmitRequest())
