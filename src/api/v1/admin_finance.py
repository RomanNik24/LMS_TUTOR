"""Роутеры финансов и статистики (docs/08 §5.8): заработок, CSV, отмены, журнал аудита.

Финансовые эндпоинты и журнал аудита — только ``owner`` (менеджер получает 403). Статистика отмен
доступна всему персоналу и денег не содержит.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from src.api.deps import OwnerActor, StaffActor, get_stats_service
from src.api.v1.responses import error_responses
from src.core.constants import LIST_LIMIT_DEFAULT
from src.schemas.finance import AuditPage, CancellationStats, EarningsGroupBy, EarningsReport
from src.services.stats import StatsService

finance_router = APIRouter(prefix="/admin/finance", tags=["admin-finance"])
stats_router = APIRouter(prefix="/admin/stats", tags=["admin-stats"])
audit_router = APIRouter(prefix="/admin/audit", tags=["admin-audit"])

Stats = Annotated[StatsService, Depends(get_stats_service)]
Start = Annotated[datetime, Query(alias="from")]
End = Annotated[datetime, Query(alias="to")]

CSV_MEDIA_TYPE = "text/csv; charset=utf-8"
CSV_FILENAME = "earnings.csv"


@finance_router.get(
    "/earnings",
    response_model=EarningsReport,
    summary="Заработано и ожидается",
    operation_id="get_earnings",
    responses=error_responses(401, 403, 422, 429),
)
async def get_earnings(
    actor: OwnerActor,
    service: Stats,
    start: Start,
    end: End,
    group_by: Annotated[EarningsGroupBy, Query()] = EarningsGroupBy.MONTH,
) -> EarningsReport:
    """Суммы за ``[from, to)`` с разрезом по ученику, предмету, неделе или месяцу."""
    return await service.earnings(actor, start, end, group_by)


@finance_router.get(
    "/export.csv",
    summary="Экспорт заработка в CSV",
    operation_id="export_earnings_csv",
    response_class=Response,
    responses={
        200: {"content": {"text/csv": {"schema": {"type": "string"}}}},
        **error_responses(401, 403, 422, 429),
    },
)
async def export_earnings_csv(
    actor: OwnerActor, service: Stats, start: Start, end: End
) -> Response:
    """CSV с колонками «Дата, Ученик, Предмет, Сумма»; период не больше года."""
    content = await service.export_csv(actor, start, end)
    return Response(
        content="﻿" + content,  # BOM: Excel открывает кириллицу в UTF-8 без «кракозябр»
        media_type=CSV_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{CSV_FILENAME}"'},
    )


@stats_router.get(
    "/cancellations",
    response_model=CancellationStats,
    summary="Статистика отмен",
    operation_id="get_cancellation_stats",
    responses=error_responses(401, 403, 422, 429),
)
async def get_cancellation_stats(
    actor: StaffActor, service: Stats, start: Start, end: End
) -> CancellationStats:
    """Число отменённых занятий за период и ученики с наибольшим числом отмен."""
    return await service.cancellations(actor, start, end)


@audit_router.get(
    "",
    response_model=AuditPage,
    summary="Журнал аудита",
    operation_id="list_audit",
    responses=error_responses(401, 403, 422, 429),
)
async def list_audit(
    actor: OwnerActor,
    service: Stats,
    limit: Annotated[int, Query()] = LIST_LIMIT_DEFAULT,
    offset: Annotated[int, Query()] = 0,
) -> AuditPage:
    """Записи журнала, новые первыми."""
    return await service.list_audit(actor, limit=limit, offset=offset)
