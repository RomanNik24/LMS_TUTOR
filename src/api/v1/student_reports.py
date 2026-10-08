"""Роутер ``GET /student/reports`` (docs/08 §4): отчёт ученика для графиков.

Только собственные данные: средний процент ДЗ по неделям, доля сданных в срок, серия пробников,
посещаемость. Денег и заметок преподавателя в ответе нет.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from src.api.deps import StudentActor, get_stats_service
from src.api.v1.responses import error_responses
from src.schemas.reports import StudentReport
from src.services.stats import StatsService

router = APIRouter(prefix="/student/reports", tags=["student-reports"])


@router.get(
    "",
    response_model=StudentReport,
    summary="Мой отчёт за период",
    operation_id="get_student_report",
    responses=error_responses(400, 401, 403, 422, 429),
)
async def get_student_report(
    actor: StudentActor,
    service: Annotated[StatsService, Depends(get_stats_service)],
    start: Annotated[datetime, Query(alias="from")],
    end: Annotated[datetime, Query(alias="to")],
) -> StudentReport:
    """Данные для графиков за ``[from, to)``; период не больше года."""
    return await service.my_report(actor, start, end)
