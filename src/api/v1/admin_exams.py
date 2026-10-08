"""Роутер ``/admin/mock-exams`` (docs/08 §5.6): результаты пробных экзаменов, роли owner и manager.

Результаты, созданные из ДЗ, правятся только через оценку выдачи (400
``mock_exam_linked_to_homework``). Финансовых полей в ответах нет.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response, status

from src.api.deps import StaffActor, get_exam_service
from src.api.v1.responses import error_responses
from src.core.constants import LIST_LIMIT_DEFAULT
from src.schemas.exams import (
    ConvertRequest,
    MockExamCreate,
    MockExamItem,
    MockExamPage,
    MockExamUpdate,
    ScoreConversion,
)
from src.services.exams import ExamService

router = APIRouter(prefix="/admin/mock-exams", tags=["admin-mock-exams"])

Exams = Annotated[ExamService, Depends(get_exam_service)]
ResultId = Annotated[int, Path(ge=1)]


@router.get(
    "",
    response_model=MockExamPage,
    summary="Результаты пробников",
    operation_id="list_mock_exams",
    responses=error_responses(401, 403, 422, 429),
)
async def list_mock_exams(
    actor: StaffActor,
    service: Exams,
    student_id: Annotated[int | None, Query(ge=1)] = None,
    exam_type_id: Annotated[int | None, Query(ge=1)] = None,
    limit: Annotated[int, Query()] = LIST_LIMIT_DEFAULT,
    offset: Annotated[int, Query()] = 0,
) -> MockExamPage:
    """Результаты с фильтрами по ученику и типу экзамена, новые первыми."""
    return await service.list_results(
        actor, student_id=student_id, exam_type_id=exam_type_id, limit=limit, offset=offset
    )


@router.post(
    "",
    response_model=MockExamItem,
    status_code=status.HTTP_201_CREATED,
    summary="Ввести результат пробника",
    operation_id="create_mock_exam",
    responses=error_responses(400, 401, 403, 404, 422, 429),
)
async def create_mock_exam(body: MockExamCreate, actor: StaffActor, service: Exams) -> MockExamItem:
    """Ручной ввод без ДЗ; ответ содержит ``converted_value`` и ``scale_applicable``."""
    return await service.record_mock_result(actor, body)


@router.post(
    "/convert",
    response_model=ScoreConversion,
    summary="Предпросмотр конвертации баллов",
    operation_id="convert_mock_exam_score",
    responses=error_responses(400, 401, 403, 404, 422, 429),
)
async def convert_mock_exam_score(
    body: ConvertRequest, actor: StaffActor, service: Exams
) -> ScoreConversion:
    """Перевод первичного балла по шкале без сохранения (форма ввода показывает результат сразу)."""
    return await service.preview(actor, body)


@router.patch(
    "/{result_id}",
    response_model=MockExamItem,
    summary="Исправить результат пробника",
    operation_id="update_mock_exam",
    responses=error_responses(400, 401, 403, 404, 422, 429),
)
async def update_mock_exam(
    result_id: ResultId, body: MockExamUpdate, actor: StaffActor, service: Exams
) -> MockExamItem:
    """Исправление ручного результата; связанные с ДЗ — только через оценку."""
    return await service.update_mock_result(actor, result_id, body)


@router.delete(
    "/{result_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить результат пробника",
    operation_id="delete_mock_exam",
    responses=error_responses(400, 401, 403, 404, 422, 429),
)
async def delete_mock_exam(result_id: ResultId, actor: StaffActor, service: Exams) -> Response:
    """Удалить ручной результат (созданные из ДЗ удалять нельзя)."""
    await service.delete_mock_result(actor, result_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
