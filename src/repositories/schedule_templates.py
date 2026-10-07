"""Репозиторий шаблонов расписания и их участников (docs/04 §3)."""

from collections.abc import Collection

from sqlalchemy import delete, select

from src.db.models import ScheduleTemplate, ScheduleTemplateParticipant
from src.repositories.base import BaseRepository


class ScheduleTemplateRepository(BaseRepository[ScheduleTemplate]):
    """Доступ к таблицам ``schedule_templates`` и ``schedule_template_participants``."""

    async def get_by_id(
        self, template_id: int, *, for_update: bool = False
    ) -> ScheduleTemplate | None:
        """Шаблон по id; ``for_update`` блокирует строку на время транзакции."""
        stmt = select(ScheduleTemplate).where(ScheduleTemplate.id == template_id)
        if for_update:
            stmt = stmt.with_for_update()
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_all(self, *, only_active: bool = False) -> list[ScheduleTemplate]:
        """Шаблоны по возрастанию id; при ``only_active`` — только включённые."""
        stmt = select(ScheduleTemplate).order_by(ScheduleTemplate.id)
        if only_active:
            stmt = stmt.where(ScheduleTemplate.is_active.is_(True))
        return list((await self._session.execute(stmt)).scalars())

    async def student_ids(self, template_id: int) -> list[int]:
        """``student_id`` участников шаблона по возрастанию."""
        stmt = (
            select(ScheduleTemplateParticipant.student_id)
            .where(ScheduleTemplateParticipant.template_id == template_id)
            .order_by(ScheduleTemplateParticipant.student_id)
        )
        return list((await self._session.execute(stmt)).scalars())

    async def replace_participants(self, template_id: int, student_ids: Collection[int]) -> None:
        """Заменить участников шаблона заданным набором."""
        await self._session.execute(
            delete(ScheduleTemplateParticipant).where(
                ScheduleTemplateParticipant.template_id == template_id
            )
        )
        self._session.add_all(
            [
                ScheduleTemplateParticipant(template_id=template_id, student_id=sid)
                for sid in sorted(student_ids)
            ]
        )
        await self._session.flush()
