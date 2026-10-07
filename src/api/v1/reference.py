"""Роутер справочников ``/reference/*`` (docs/08 §3): предметы и типы экзаменов."""

from typing import Annotated

from fastapi import APIRouter, Depends

from src.api.deps import current_user, get_reference_service
from src.api.v1.responses import error_responses
from src.core.current_user import CurrentUser
from src.schemas.reference import ExamTypeItem, SubjectItem
from src.services.reference import ReferenceService

router = APIRouter(prefix="/reference", tags=["reference"])


@router.get(
    "/subjects",
    response_model=list[SubjectItem],
    summary="Предметы",
    operation_id="list_subjects",
    responses=error_responses(401, 429),
)
async def list_subjects(
    user: Annotated[CurrentUser, Depends(current_user)],
    reference: Annotated[ReferenceService, Depends(get_reference_service)],
) -> list[SubjectItem]:
    """Активные предметы: код и название."""
    return await reference.list_subjects(user)


@router.get(
    "/exam-types",
    response_model=list[ExamTypeItem],
    summary="Типы экзаменов",
    operation_id="list_exam_types",
    responses=error_responses(401, 429),
)
async def list_exam_types(
    user: Annotated[CurrentUser, Depends(current_user)],
    reference: Annotated[ReferenceService, Depends(get_reference_service)],
) -> list[ExamTypeItem]:
    """Активные типы экзаменов: код, предмет, вид, формат результата, максимальный балл."""
    return await reference.list_exam_types(user)
