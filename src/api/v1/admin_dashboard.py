"""Роутер ``GET /admin/dashboard/today`` (docs/08 §5.1): дашборд «Сегодня» для персонала.

Владелец получает ``DashboardOwner`` (с ``earned_month`` и ``expected_month``), менеджер —
``DashboardStaff``, где финансовых полей нет.
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from src.api.deps import StaffActor, get_dashboard_service
from src.api.v1.responses import error_responses
from src.schemas.dashboard import DashboardOwner, DashboardStaff
from src.services.dashboard import DashboardService

router = APIRouter(prefix="/admin/dashboard", tags=["admin-dashboard"])


@router.get(
    "/today",
    response_model=DashboardOwner | DashboardStaff,
    summary="Дашборд «Сегодня»",
    operation_id="get_today_dashboard",
    responses=error_responses(401, 403, 429),
)
async def get_today_dashboard(
    actor: StaffActor,
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
) -> DashboardStaff:
    """Пять блоков дня; у владельца — ещё заработано и ожидается за месяц."""
    return await service.get_today_dashboard(actor)
