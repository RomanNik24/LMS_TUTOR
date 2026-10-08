"""``ExamService``: пробные экзамены и перевод первичных баллов (docs/04 §6, docs/01 US-06).

Шкалы НЕ хардкодятся: значение берётся из ``grade_scales`` по году экзамена (docs/04 §1.3).
Правила (docs/04 §6):
1. ``max_primary`` результата отличается от ``exam_types.max_primary`` — конвертация не
   применяется (``converted_value = NULL``);
2. иначе значение — из шкалы с наибольшим ``valid_year <= год экзамена``;
3. ОГЭ математика: ``geometry_score < config.min_geometry`` → итоговая оценка 2 при любой сумме;
   если баллы по геометрии не указаны, расчёт по сумме и предупреждение;
4. при оценке ДЗ типа ``mock_exam`` результат создаётся или обновляется автоматически.

Результаты, созданные из ДЗ (``assignment_id`` задан), правятся только через оценку выдачи.
Commit делает только этот сервис (в ``record_from_assignment`` — вызывающий ``GradingService``).
"""

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from src.core import texts
from src.core.constants import LIST_LIMIT_DEFAULT, LIST_LIMIT_MAX
from src.core.current_user import CurrentUser
from src.core.enums import UserRole
from src.core.exceptions import (
    BusinessRuleError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from src.core.timeutils import local_date_of, utcnow
from src.db.models import ExamType, Homework, HomeworkAssignment, MockExamResult
from src.repositories.exams import GradeScaleRepository, MockExamRepository
from src.repositories.homework import ExamTypeRepository
from src.repositories.users import UserRepository
from src.schemas.exams import (
    ConversionWarning,
    ConvertRequest,
    MockExamCreate,
    MockExamItem,
    MockExamPage,
    MockExamUpdate,
    ScoreConversion,
)
from src.services.auth import STAFF_ROLES

MIN_PASSING_GRADE = 2


def _min_geometry(exam_type: ExamType) -> int | None:
    value = exam_type.config.get("min_geometry")
    return value if isinstance(value, int) else None


class ExamService:
    """Результаты пробников персонала и конвертация баллов."""

    def __init__(self, session: AsyncSession) -> None:
        """Создать сервис на сессию текущей единицы работы."""
        self._session = session
        self._scales = GradeScaleRepository(session)
        self._results = MockExamRepository(session)
        self._exam_types = ExamTypeRepository(session)
        self._users = UserRepository(session)

    # ------------------------------------------------------------------ конвертация

    async def convert_score(
        self,
        exam_type: ExamType,
        *,
        exam_date: date,
        primary_score: int,
        max_primary: int,
        geometry_score: int | None = None,
    ) -> ScoreConversion:
        """Перевести первичный балл в оценку или тестовый балл.

        Args:
            exam_type: Тип экзамена (с ``max_primary`` и ``config``).
            exam_date: Дата экзамена: по её году выбирается шкала.
            primary_score: Первичный балл.
            max_primary: Максимум этого варианта.
            geometry_score: Баллы по геометрии (только ОГЭ математика).
        """
        if max_primary != exam_type.max_primary:
            return ScoreConversion(converted_value=None, scale_year=None, scale_applicable=False)
        found = await self._scales.lookup(exam_type.id, exam_date.year, primary_score)
        if found is None:
            return ScoreConversion(converted_value=None, scale_year=None, scale_applicable=False)
        scale_year, value = found
        warning: ConversionWarning | None = None
        min_geometry = _min_geometry(exam_type)
        if min_geometry is not None:
            if geometry_score is None:
                warning = ConversionWarning.GEOMETRY_MISSING
            elif geometry_score < min_geometry:
                value = min(value, MIN_PASSING_GRADE)
        return ScoreConversion(
            converted_value=value, scale_year=scale_year, scale_applicable=True, warning=warning
        )

    async def preview(self, actor: CurrentUser, data: ConvertRequest) -> ScoreConversion:
        """Конвертация без сохранения: мгновенный показ в форме ввода пробника.

        Raises:
            PermissionDeniedError: Не сотрудник.
            NotFoundError: ``exam_type_not_found``.
            BusinessRuleError: ``score_out_of_range``.
            ValidationError: ``geometry_not_applicable``, ``geometry_too_big``.
        """
        self._require_staff(actor)
        exam_type = await self._active_exam_type(data.exam_type_id)
        self._validate(exam_type, data.primary_score, data.max_primary, data.geometry_score)
        return await self.convert_score(
            exam_type,
            exam_date=data.exam_date,
            primary_score=data.primary_score,
            max_primary=data.max_primary,
            geometry_score=data.geometry_score,
        )

    # ------------------------------------------------------------------ результаты

    async def record_mock_result(self, actor: CurrentUser, data: MockExamCreate) -> MockExamItem:
        """Ввести результат пробника без ДЗ (``assignment_id`` пуст).

        Raises:
            PermissionDeniedError: Не сотрудник.
            NotFoundError: ``student_not_found``, ``exam_type_not_found``.
            BusinessRuleError: ``score_out_of_range``.
            ValidationError: ``geometry_not_applicable``, ``geometry_too_big``.
        """
        self._require_staff(actor)
        student = await self._users.get_by_id(data.student_id)
        if student is None or student.role != UserRole.STUDENT or not student.is_active:
            raise NotFoundError(texts.STUDENT_NOT_FOUND, code="student_not_found")
        exam_type = await self._active_exam_type(data.exam_type_id)
        self._validate(exam_type, data.primary_score, data.max_primary, data.geometry_score)
        result = MockExamResult(
            student_id=student.id,
            exam_type_id=exam_type.id,
            exam_date=data.exam_date,
            primary_score=data.primary_score,
            max_primary=data.max_primary,
            geometry_score=data.geometry_score,
            comment=data.comment,
            created_by=actor.id,
        )
        await self._apply_conversion(result, exam_type)
        self._session.add(result)
        await self._session.flush()
        item = self._item(result, exam_type, student.display_name)
        await self._session.commit()
        return item

    async def update_mock_result(
        self, actor: CurrentUser, result_id: int, data: MockExamUpdate
    ) -> MockExamItem:
        """Исправить ручной результат; созданный из ДЗ правится через оценку выдачи.

        Raises:
            PermissionDeniedError: Не сотрудник.
            NotFoundError: ``mock_exam_not_found``.
            BusinessRuleError: ``mock_exam_linked_to_homework``, ``score_out_of_range``.
        """
        self._require_staff(actor)
        result = await self._manual_for_update(result_id)
        exam_type = await self._exam_types.get_by_id(result.exam_type_id)
        if exam_type is None:  # внешний ключ гарантирует наличие; защита от гонки
            raise NotFoundError(texts.MOCK_EXAM_EXAM_TYPE_UNKNOWN, code="exam_type_not_found")
        changed = data.model_fields_set
        if "exam_date" in changed and data.exam_date is not None:
            result.exam_date = data.exam_date
        if "primary_score" in changed and data.primary_score is not None:
            result.primary_score = data.primary_score
        if "max_primary" in changed and data.max_primary is not None:
            result.max_primary = data.max_primary
        if "geometry_score" in changed:
            result.geometry_score = data.geometry_score
        if "comment" in changed:
            comment = data.comment
            result.comment = None if comment is None or not comment.strip() else comment.strip()
        self._validate(exam_type, result.primary_score, result.max_primary, result.geometry_score)
        await self._apply_conversion(result, exam_type)
        result.updated_at = utcnow()
        await self._session.flush()
        row = await self._results.row(result.id)
        if row is None:  # строка только что найдена под блокировкой
            raise NotFoundError(texts.MOCK_EXAM_NOT_FOUND, code="mock_exam_not_found")
        item = self._item(*row)
        await self._session.commit()
        return item

    async def delete_mock_result(self, actor: CurrentUser, result_id: int) -> None:
        """Удалить ручной результат (созданные из ДЗ удалять нельзя).

        Raises:
            PermissionDeniedError: Не сотрудник.
            NotFoundError: ``mock_exam_not_found``.
            BusinessRuleError: ``mock_exam_linked_to_homework``.
        """
        self._require_staff(actor)
        result = await self._manual_for_update(result_id)
        await self._results.delete(result)
        await self._session.commit()

    async def list_results(
        self,
        actor: CurrentUser,
        *,
        student_id: int | None = None,
        exam_type_id: int | None = None,
        limit: int = LIST_LIMIT_DEFAULT,
        offset: int = 0,
    ) -> MockExamPage:
        """Результаты пробников с фильтрами по ученику и экзамену (новые первыми).

        Raises:
            PermissionDeniedError: Не сотрудник.
            ValidationError: ``invalid_list_params``.
        """
        self._require_staff(actor)
        if not 1 <= limit <= LIST_LIMIT_MAX or offset < 0:
            raise ValidationError(texts.LIST_PARAMS_INVALID, code="invalid_list_params")
        rows, total = await self._results.page(
            student_id=student_id, exam_type_id=exam_type_id, limit=limit, offset=offset
        )
        return MockExamPage(
            items=[self._item(*row) for row in rows], total=total, limit=limit, offset=offset
        )

    # ------------------------------------------------------------------ из оценки ДЗ

    async def check_homework_grade(
        self, homework: Homework, score: int, geometry_score: int | None
    ) -> None:
        """Проверить оценку ДЗ до изменения выдачи: баллы по геометрии и тип экзамена.

        Для обычного ДЗ (без ``exam_type_id``) баллы по геометрии недопустимы.

        Raises:
            NotFoundError: ``exam_type_not_found``.
            BusinessRuleError: ``score_out_of_range``.
            ValidationError: ``geometry_not_applicable``, ``geometry_too_big``.
        """
        if homework.exam_type_id is None:
            if geometry_score is not None:
                raise ValidationError(
                    texts.MOCK_EXAM_GEOMETRY_NOT_APPLICABLE, code="geometry_not_applicable"
                )
            return
        exam_type = await self._exam_types.get_by_id(homework.exam_type_id)
        if exam_type is None:
            raise NotFoundError(texts.MOCK_EXAM_EXAM_TYPE_UNKNOWN, code="exam_type_not_found")
        self._validate(exam_type, score, homework.max_score, geometry_score)

    async def record_from_assignment(
        self,
        assignment: HomeworkAssignment,
        homework: Homework,
        *,
        graded_by: int,
        geometry_score: int | None,
    ) -> ScoreConversion:
        """Создать или обновить результат при оценке ДЗ типа ``mock_exam`` (docs/04 §6, п. 4).

        Вызывается из транзакции ``GradingService``: ``commit`` делает вызывающий. Дата экзамена
        — дата первой оценки в поясе ученика; повторная оценка обновляет баллы и шкалу.

        Raises:
            NotFoundError: ``exam_type_not_found``.
            BusinessRuleError: ``score_out_of_range``.
            ValidationError: ``geometry_not_applicable``, ``geometry_too_big``.
        """
        if homework.exam_type_id is None or assignment.score is None:
            raise NotFoundError(texts.MOCK_EXAM_EXAM_TYPE_UNKNOWN, code="exam_type_not_found")
        exam_type = await self._exam_types.get_by_id(homework.exam_type_id)
        if exam_type is None:
            raise NotFoundError(texts.MOCK_EXAM_EXAM_TYPE_UNKNOWN, code="exam_type_not_found")
        self._validate(exam_type, assignment.score, homework.max_score, geometry_score)
        result = await self._results.get_by_assignment(assignment.id)
        if result is None:
            student = await self._users.get_by_id(assignment.student_id)
            timezone = student.timezone if student is not None else "UTC"
            result = MockExamResult(
                student_id=assignment.student_id,
                exam_type_id=exam_type.id,
                exam_date=local_date_of(utcnow(), timezone),
                primary_score=assignment.score,
                max_primary=homework.max_score,
                assignment_id=assignment.id,
                created_by=graded_by,
            )
            self._session.add(result)
        result.primary_score = assignment.score
        result.max_primary = homework.max_score
        result.geometry_score = geometry_score
        result.updated_at = utcnow()
        conversion = await self._apply_conversion(result, exam_type)
        await self._session.flush()
        return conversion

    # ------------------------------------------------------------------ внутреннее

    @staticmethod
    def _require_staff(actor: CurrentUser) -> None:
        if actor.role not in STAFF_ROLES:
            raise PermissionDeniedError()

    async def _active_exam_type(self, exam_type_id: int) -> ExamType:
        exam_type = await self._exam_types.get_by_id(exam_type_id)
        if exam_type is None or not exam_type.is_active:
            raise NotFoundError(texts.MOCK_EXAM_EXAM_TYPE_UNKNOWN, code="exam_type_not_found")
        return exam_type

    async def _manual_for_update(self, result_id: int) -> MockExamResult:
        result = await self._results.get_by_id(result_id, for_update=True)
        if result is None:
            raise NotFoundError(texts.MOCK_EXAM_NOT_FOUND, code="mock_exam_not_found")
        if result.assignment_id is not None:
            raise BusinessRuleError(
                texts.MOCK_EXAM_LINKED_TO_HOMEWORK, code="mock_exam_linked_to_homework"
            )
        return result

    @staticmethod
    def _validate(
        exam_type: ExamType, primary_score: int, max_primary: int, geometry_score: int | None
    ) -> None:
        if primary_score > max_primary:
            raise BusinessRuleError(
                texts.MOCK_EXAM_SCORE_ABOVE_MAX,
                code="score_out_of_range",
                details={"max_primary": max_primary},
            )
        if geometry_score is None:
            return
        if _min_geometry(exam_type) is None:
            raise ValidationError(
                texts.MOCK_EXAM_GEOMETRY_NOT_APPLICABLE, code="geometry_not_applicable"
            )
        if geometry_score > primary_score:
            raise ValidationError(texts.MOCK_EXAM_GEOMETRY_TOO_BIG, code="geometry_too_big")

    async def _apply_conversion(
        self, result: MockExamResult, exam_type: ExamType
    ) -> ScoreConversion:
        conversion = await self.convert_score(
            exam_type,
            exam_date=result.exam_date,
            primary_score=result.primary_score,
            max_primary=result.max_primary,
            geometry_score=result.geometry_score,
        )
        result.converted_value = conversion.converted_value
        result.scale_year = conversion.scale_year
        return conversion

    @staticmethod
    def _item(result: MockExamResult, exam_type: ExamType, student_name: str) -> MockExamItem:
        applicable = result.converted_value is not None
        warning = (
            ConversionWarning.GEOMETRY_MISSING
            if applicable and _min_geometry(exam_type) is not None and result.geometry_score is None
            else None
        )
        return MockExamItem(
            id=result.id,
            student_id=result.student_id,
            student_name=student_name,
            exam_type_id=exam_type.id,
            exam_type_code=exam_type.code,
            exam_type_name=exam_type.name,
            exam_date=result.exam_date,
            primary_score=result.primary_score,
            max_primary=result.max_primary,
            geometry_score=result.geometry_score,
            converted_value=result.converted_value,
            scale_year=result.scale_year,
            scale_applicable=applicable,
            warning=warning,
            assignment_id=result.assignment_id,
            comment=result.comment,
        )
