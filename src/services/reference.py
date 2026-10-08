"""``ReferenceService``: справочники предметов и типов экзаменов (docs/08 §3, docs/04 §1).

Предметы и экзамены — данные в БД (docs/06 A4): фронтенд берёт их отсюда, а не из своего кода.
Читать справочники может любой вошедший пользователь; цен и личных данных в них нет.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.current_user import CurrentUser
from src.repositories.homework import ExamTypeRepository
from src.repositories.subjects import SubjectRepository
from src.schemas.reference import ExamTypeItem, SubjectItem


class ReferenceService:
    """Чтение справочников."""

    def __init__(self, session: AsyncSession) -> None:
        """Создать сервис на сессию запроса."""
        self._subjects = SubjectRepository(session)
        self._exam_types = ExamTypeRepository(session)

    async def list_subjects(self, actor: CurrentUser) -> list[SubjectItem]:
        """Активные предметы.

        Args:
            actor: Текущий пользователь (любая роль: справочник общий).
        """
        del actor  # права проверены зависимостью: нужен только вход
        return [
            SubjectItem.model_validate(subject) for subject in await self._subjects.list_active()
        ]

    async def list_exam_types(self, actor: CurrentUser) -> list[ExamTypeItem]:
        """Активные типы экзаменов с кодом предмета.

        Args:
            actor: Текущий пользователь (любая роль: справочник общий).
        """
        del actor
        return [
            ExamTypeItem(
                id=exam_type.id,
                code=exam_type.code,
                subject_code=subject_code,
                kind=exam_type.kind,
                result_kind=exam_type.result_kind,
                max_primary=exam_type.max_primary,
                name=exam_type.name,
                uses_geometry=isinstance(exam_type.config.get("min_geometry"), int),
            )
            for exam_type, subject_code in await self._exam_types.list_active_with_subject_codes()
        ]
