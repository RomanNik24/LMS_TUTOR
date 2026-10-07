"""``FileService``: файлы домашних заданий (T4.05, docs/09, docs/08 §6, §8).

Правила:
- тип файла определяется по СОДЕРЖИМОМУ (JPEG, PNG, HEIC, PDF), расширение и ``Content-Type`` из
  запроса не доверяются; другой тип — 415 ``unsupported_file_type``;
- размер ≤ 10 МБ (иначе 413 ``file_too_large``), у выдачи не больше 10 файлов решения;
- фото: HEIC → JPEG, поворот по EXIF, длинная сторона ≤ 2400 px (в потоке, event loop свободен);
- ключ в S3 — UUID с безопасным расширением; исходное имя хранится в БД только для показа и
  очищается от путей и управляющих символов;
- права: решение загружает и удаляет только ученик-владелец выдачи (пока она ``assigned`` или
  ``needs_revision``), файл проверки и материал — только персонал; читать файл выдачи может
  её ученик и персонал; чужой файл — 404 (docs/08 §1);
- commit выполняет только этот сервис, один публичный метод = одна транзакция.
"""

import logging
import re

from sqlalchemy.ext.asyncio import AsyncSession

from src.core import texts
from src.core.constants import S3_PRESIGN_TTL_SECONDS
from src.core.current_user import CurrentUser
from src.core.enums import AssignmentStatus, HomeworkFileRole, UserRole
from src.core.exceptions import (
    AppError,
    BusinessRuleError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from src.core.file_types import (
    ALLOWED_TYPES,
    IMAGE_TYPES,
    JPEG,
    MAX_FILE_BYTES,
    MAX_SOLUTION_FILES,
    detect_content_type,
)
from src.core.images import ImageProcessingError, prepare_image
from src.core.storage import ObjectStorage, homework_key, material_key
from src.db.models import HomeworkAssignment, HomeworkFile, HomeworkMaterial
from src.repositories.homework import (
    HomeworkAssignmentRepository,
    HomeworkFileRepository,
    HomeworkMaterialRepository,
    HomeworkRepository,
)
from src.schemas.files import FileUrl, HomeworkFileItem, MaterialItem
from src.services.auth import STAFF_ROLES

logger = logging.getLogger(__name__)

EDITABLE_STATUSES = frozenset({AssignmentStatus.ASSIGNED, AssignmentStatus.NEEDS_REVISION})
_NAME_MAX = 255
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_EXTENSIONS = {"image/jpeg": "jpg", "application/pdf": "pdf"}


class PreparedFile:
    """Проверенное содержимое, готовое к сохранению."""

    def __init__(self, data: bytes, content_type: str, name: str) -> None:
        """Сохранить байты, определённый тип и очищенное имя для показа."""
        self.data = data
        self.content_type = content_type
        self.name = name
        self.extension = _EXTENSIONS[content_type]


def display_name(filename: str) -> str:
    """Имя для показа: без путей и управляющих символов, не длиннее 255 символов."""
    base = filename.replace("\\", "/").rsplit("/", 1)[-1]
    cleaned = _CONTROL_CHARS.sub("", base).strip()
    return (cleaned or texts.FILE_DEFAULT_NAME)[:_NAME_MAX]


async def prepare_upload(filename: str, data: bytes) -> PreparedFile:
    """Проверить и подготовить загружаемый файл.

    Raises:
        ValidationError: ``empty_file`` — пустой файл.
        AppError: 413 ``file_too_large``; 415 ``unsupported_file_type``.
    """
    if not data:
        raise ValidationError(texts.FILE_EMPTY, code="empty_file")
    if len(data) > MAX_FILE_BYTES:
        raise AppError(texts.FILE_TOO_LARGE, code="file_too_large", http_status=413)
    content_type = detect_content_type(data)
    if content_type is None or content_type not in ALLOWED_TYPES:
        raise AppError(texts.FILE_UNSUPPORTED, code="unsupported_file_type", http_status=415)
    if content_type in IMAGE_TYPES:
        try:
            data = await prepare_image(data)
        except ImageProcessingError as error:
            raise AppError(
                texts.FILE_UNSUPPORTED, code="unsupported_file_type", http_status=415
            ) from error
        content_type = JPEG
    return PreparedFile(data, content_type, display_name(filename))


class FileService:
    """Загрузка, удаление и выдача ссылок на файлы заданий."""

    def __init__(self, session: AsyncSession, storage: ObjectStorage) -> None:
        """Создать сервис.

        Args:
            session: Сессия БД на текущую единицу работы.
            storage: Хранилище файлов (S3 или подмена в тестах).
        """
        self._session = session
        self._storage = storage
        self._homeworks = HomeworkRepository(session)
        self._assignments = HomeworkAssignmentRepository(session)
        self._files = HomeworkFileRepository(session)
        self._materials = HomeworkMaterialRepository(session)

    # ------------------------------------------------------------------ загрузка

    async def upload_solution(
        self, actor: CurrentUser, assignment_id: int, filename: str, data: bytes
    ) -> HomeworkFileItem:
        """Загрузить файл решения (только ученик-владелец, пока выдача редактируема).

        Raises:
            PermissionDeniedError: Не ученик.
            NotFoundError: ``assignment_not_found`` (в том числе чужая выдача).
            BusinessRuleError: ``assignment_not_editable``; ``files_limit`` — уже 10 файлов.
            AppError: 413 ``file_too_large``, 415 ``unsupported_file_type``.
        """
        self._require_student(actor)
        await self._own_assignment(actor, assignment_id)
        prepared = await prepare_upload(filename, data)
        assignment = await self._lock_editable(actor, assignment_id)
        used = await self._files.count_for(assignment.id, HomeworkFileRole.STUDENT_SOLUTION)
        if used >= MAX_SOLUTION_FILES:
            raise BusinessRuleError(texts.FILES_LIMIT, code="files_limit")
        return await self._store_file(
            actor, assignment.id, HomeworkFileRole.STUDENT_SOLUTION, prepared
        )

    async def upload_review(
        self, actor: CurrentUser, assignment_id: int, filename: str, data: bytes
    ) -> HomeworkFileItem:
        """Загрузить файл проверки (только персонал).

        Raises:
            PermissionDeniedError: Не сотрудник.
            NotFoundError: ``assignment_not_found``.
            AppError: 413 ``file_too_large``, 415 ``unsupported_file_type``.
        """
        self._require_staff(actor)
        assignment = await self._assignments.get_by_id(assignment_id)
        if assignment is None:
            raise NotFoundError(texts.ASSIGNMENT_NOT_FOUND, code="assignment_not_found")
        prepared = await prepare_upload(filename, data)
        return await self._store_file(
            actor, assignment.id, HomeworkFileRole.TEACHER_REVIEW, prepared
        )

    async def upload_material(
        self, actor: CurrentUser, homework_id: int, filename: str, data: bytes
    ) -> MaterialItem:
        """Загрузить материал преподавателя к заданию (только персонал).

        Raises:
            PermissionDeniedError: Не сотрудник.
            NotFoundError: ``homework_not_found``.
            AppError: 413 ``file_too_large``, 415 ``unsupported_file_type``.
        """
        self._require_staff(actor)
        if await self._homeworks.get_by_id(homework_id) is None:
            raise NotFoundError(texts.HOMEWORK_NOT_FOUND, code="homework_not_found")
        prepared = await prepare_upload(filename, data)
        key = material_key(homework_id, prepared.extension)
        await self._storage.put(key, prepared.data, prepared.content_type)
        try:
            material = await self._materials.add(
                HomeworkMaterial(
                    homework_id=homework_id,
                    s3_key=key,
                    original_name=prepared.name,
                    content_type=prepared.content_type,
                    size_bytes=len(prepared.data),
                )
            )
            await self._session.commit()
        except Exception:
            await self._discard(key)
            raise
        return MaterialItem(
            id=material.id,
            homework_id=homework_id,
            original_name=material.original_name,
            content_type=material.content_type,
            size_bytes=material.size_bytes,
        )

    # ------------------------------------------------------------------ удаление

    async def delete_solution(self, actor: CurrentUser, assignment_id: int, file_id: int) -> None:
        """Удалить свой файл решения (пока выдача редактируема).

        Raises:
            PermissionDeniedError: Не ученик.
            NotFoundError: ``assignment_not_found`` или ``file_not_found`` (чужой файл — тоже).
            BusinessRuleError: ``assignment_not_editable``.
        """
        self._require_student(actor)
        await self._lock_editable(actor, assignment_id)
        file = await self._files.get_by_id(file_id)
        if (
            file is None
            or file.assignment_id != assignment_id
            or file.role != HomeworkFileRole.STUDENT_SOLUTION
        ):
            raise NotFoundError(texts.FILE_NOT_FOUND, code="file_not_found")
        key = file.s3_key
        await self._files.delete(file)
        await self._session.commit()
        await self._discard(key)

    # ------------------------------------------------------------------ чтение

    async def file_url(self, actor: CurrentUser, file_id: int) -> FileUrl:
        """Подписанная ссылка на файл выдачи: ученик — только по своей выдаче, персонал — любую.

        Raises:
            NotFoundError: ``file_not_found`` (чужой и несуществующий файл неотличимы).
        """
        file = await self._files.get_by_id(file_id)
        if file is None:
            raise NotFoundError(texts.FILE_NOT_FOUND, code="file_not_found")
        if actor.role not in STAFF_ROLES:
            assignment = await self._assignments.get_by_id(file.assignment_id)
            if (
                actor.role != UserRole.STUDENT
                or assignment is None
                or assignment.student_id != actor.id
            ):
                raise NotFoundError(texts.FILE_NOT_FOUND, code="file_not_found")
        return await self._signed(file.s3_key)

    async def material_url(self, actor: CurrentUser, material_id: int) -> FileUrl:
        """Ссылка на материал: ученик — если задание выдано ему, персонал — любой материал.

        Raises:
            NotFoundError: ``file_not_found``.
        """
        material = await self._materials.get_by_id(material_id)
        if material is None:
            raise NotFoundError(texts.FILE_NOT_FOUND, code="file_not_found")
        if actor.role not in STAFF_ROLES and not (
            actor.role == UserRole.STUDENT
            and await self._homeworks.student_has_assignment(material.homework_id, actor.id)
        ):
            raise NotFoundError(texts.FILE_NOT_FOUND, code="file_not_found")
        return await self._signed(material.s3_key)

    # ------------------------------------------------------------------ внутреннее

    @staticmethod
    def _require_student(actor: CurrentUser) -> None:
        if actor.role != UserRole.STUDENT:
            raise PermissionDeniedError()

    @staticmethod
    def _require_staff(actor: CurrentUser) -> None:
        if actor.role not in STAFF_ROLES:
            raise PermissionDeniedError()

    async def _own_assignment(self, actor: CurrentUser, assignment_id: int) -> HomeworkAssignment:
        assignment = await self._assignments.get_by_id(assignment_id)
        if assignment is None or assignment.student_id != actor.id:
            raise NotFoundError(texts.ASSIGNMENT_NOT_FOUND, code="assignment_not_found")
        return assignment

    async def _lock_editable(self, actor: CurrentUser, assignment_id: int) -> HomeworkAssignment:
        """Своя выдача под блокировкой; файлы меняют, пока она assigned или needs_revision."""
        assignment = await self._assignments.get_by_id(assignment_id, for_update=True)
        if assignment is None or assignment.student_id != actor.id:
            raise NotFoundError(texts.ASSIGNMENT_NOT_FOUND, code="assignment_not_found")
        if assignment.status not in EDITABLE_STATUSES:
            raise BusinessRuleError(texts.ASSIGNMENT_NOT_EDITABLE, code="assignment_not_editable")
        return assignment

    async def _store_file(
        self, actor: CurrentUser, assignment_id: int, role: HomeworkFileRole, prepared: PreparedFile
    ) -> HomeworkFileItem:
        """Сохранить объект в S3 и запись в БД; при сбое БД объект удаляется."""
        key = homework_key(assignment_id, prepared.extension)
        await self._storage.put(key, prepared.data, prepared.content_type)
        try:
            row = await self._files.add(
                HomeworkFile(
                    assignment_id=assignment_id,
                    uploaded_by=actor.id,
                    role=role,
                    s3_key=key,
                    original_name=prepared.name,
                    content_type=prepared.content_type,
                    size_bytes=len(prepared.data),
                )
            )
            await self._session.commit()
        except Exception:
            await self._discard(key)
            raise
        return HomeworkFileItem(
            id=row.id,
            assignment_id=assignment_id,
            role=row.role,
            original_name=row.original_name,
            content_type=row.content_type,
            size_bytes=row.size_bytes,
            created_at=row.created_at,
        )

    async def _signed(self, key: str) -> FileUrl:
        url = await self._storage.presign_get(key, expires=S3_PRESIGN_TTL_SECONDS)
        return FileUrl(url=url, expires_in=S3_PRESIGN_TTL_SECONDS)

    async def _discard(self, key: str) -> None:
        """Удалить объект из S3; сбой не должен ронять запрос (потерянный объект безвреден)."""
        try:
            await self._storage.delete(key)
        except Exception:  # noqa: BLE001 - лишний объект в приватном бакете не ошибка запроса
            logger.warning("Не удалось удалить объект из хранилища: %s", key)
