"""FileService (T4.05): права, лимиты, обработка файлов, ссылки (PostgreSQL + подмена хранилища)."""

import io
from datetime import UTC, datetime

import pytest
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.current_user import CurrentUser
from src.core.enums import (
    AssignmentStatus,
    DueMode,
    HomeworkFileRole,
    HomeworkKind,
    UserRole,
)
from src.core.exceptions import (
    AppError,
    BusinessRuleError,
    NotFoundError,
    PermissionDeniedError,
)
from src.core.file_types import MAX_FILE_BYTES, MAX_SOLUTION_FILES
from src.db.models import (
    Homework,
    HomeworkAssignment,
    HomeworkFile,
    HomeworkMaterial,
    Subject,
    User,
)
from src.services.files import FileService

pytestmark = pytest.mark.security

DUE = datetime(2030, 10, 14, 14, 0, tzinfo=UTC)
PDF = b"%PDF-1.4\n" + b"x" * 200


class FakeStorage:
    """Хранилище в памяти: что положили, то можно увидеть и удалить."""

    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}
        self.deleted: list[str] = []
        self.signed: list[tuple[str, int]] = []

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        self.objects[key] = (data, content_type)

    async def delete(self, key: str) -> None:
        self.deleted.append(key)
        self.objects.pop(key, None)

    async def presign_get(self, key: str, *, expires: int = 600) -> str:
        self.signed.append((key, expires))
        return f"https://files.example/{key}?exp={expires}"


def image_bytes(fmt: str = "JPEG", size: tuple[int, int] = (64, 48)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, (30, 90, 200)).save(buffer, format=fmt)
    return buffer.getvalue()


@pytest.fixture
def storage() -> FakeStorage:
    return FakeStorage()


@pytest.fixture
def service(db_session: AsyncSession, storage: FakeStorage) -> FileService:
    return FileService(db_session, storage)


async def _user(db: AsyncSession, role: UserRole, name: str) -> User:
    user = User(role=role, display_name=name)
    db.add(user)
    await db.commit()
    return user


def actor(user: User) -> CurrentUser:
    return CurrentUser(id=user.id, role=user.role, timezone=user.timezone)


@pytest.fixture
async def owner(db_session: AsyncSession) -> User:
    return await _user(db_session, UserRole.OWNER, "Роман")


@pytest.fixture
async def manager(db_session: AsyncSession) -> User:
    return await _user(db_session, UserRole.MANAGER, "Мария")


@pytest.fixture
async def anya(db_session: AsyncSession) -> User:
    return await _user(db_session, UserRole.STUDENT, "Аня")


@pytest.fixture
async def boris(db_session: AsyncSession) -> User:
    return await _user(db_session, UserRole.STUDENT, "Борис")


@pytest.fixture
async def homework(db_session: AsyncSession, owner: User) -> Homework:
    subject = Subject(code="informatics_t405", name="Информатика")
    db_session.add(subject)
    await db_session.flush()
    hw = Homework(
        created_by=owner.id,
        subject_id=subject.id,
        kind=HomeworkKind.REGULAR,
        title="Графы",
        max_score=13,
        due_mode=DueMode.FIXED,
    )
    db_session.add(hw)
    await db_session.commit()
    return hw


async def assign(
    db: AsyncSession,
    hw: Homework,
    student: User,
    status: AssignmentStatus = AssignmentStatus.ASSIGNED,
) -> HomeworkAssignment:
    row = HomeworkAssignment(
        homework_id=hw.id, student_id=student.id, original_due_at=DUE, due_at=DUE, status=status
    )
    db.add(row)
    await db.commit()
    return row


async def count(db: AsyncSession, model: type) -> int:
    return (await db.execute(select(func.count()).select_from(model))).scalar_one()


# ---------------------------------------------------------------- загрузка решения


async def test_student_uploads_jpeg_to_uuid_key(
    service: FileService,
    storage: FakeStorage,
    db_session: AsyncSession,
    homework: Homework,
    anya: User,
) -> None:
    row = await assign(db_session, homework, anya)
    item = await service.upload_solution(actor(anya), row.id, "../решение.jpg", image_bytes())
    assert item.role == HomeworkFileRole.STUDENT_SOLUTION
    assert item.original_name == "решение.jpg"  # без пути
    assert item.content_type == "image/jpeg"
    (key,) = storage.objects
    assert key.startswith(f"homework/{row.id}/")
    assert key.endswith(".jpg")
    assert "решение" not in key  # имя пользователя в ключ не попадает
    stored = (await db_session.execute(select(HomeworkFile))).scalar_one()
    assert stored.s3_key == key
    assert stored.size_bytes == len(storage.objects[key][0])


async def test_heic_is_converted_to_jpeg(
    service: FileService,
    storage: FakeStorage,
    db_session: AsyncSession,
    homework: Homework,
    anya: User,
) -> None:
    row = await assign(db_session, homework, anya)
    item = await service.upload_solution(
        actor(anya), row.id, "IMG_0001.HEIC", image_bytes("HEIF", (100, 80))
    )
    assert item.content_type == "image/jpeg"
    (key,) = storage.objects
    assert key.endswith(".jpg")
    assert storage.objects[key][0].startswith(b"\xff\xd8\xff")


async def test_large_photo_is_downscaled(
    service: FileService,
    storage: FakeStorage,
    db_session: AsyncSession,
    homework: Homework,
    anya: User,
) -> None:
    row = await assign(db_session, homework, anya)
    await service.upload_solution(actor(anya), row.id, "big.jpg", image_bytes(size=(4000, 3000)))
    stored = Image.open(io.BytesIO(next(iter(storage.objects.values()))[0]))
    assert stored.size == (2400, 1800)


async def test_pdf_is_stored_unchanged(
    service: FileService,
    storage: FakeStorage,
    db_session: AsyncSession,
    homework: Homework,
    anya: User,
) -> None:
    row = await assign(db_session, homework, anya)
    item = await service.upload_solution(actor(anya), row.id, "решение.pdf", PDF)
    assert item.content_type == "application/pdf"
    assert next(iter(storage.objects.values()))[0] == PDF


async def test_spoofed_extension_is_415_and_nothing_is_saved(
    service: FileService,
    storage: FakeStorage,
    db_session: AsyncSession,
    homework: Homework,
    anya: User,
) -> None:
    row = await assign(db_session, homework, anya)
    with pytest.raises(AppError) as raised:
        await service.upload_solution(
            actor(anya), row.id, "photo.jpg", b"MZ\x90\x00" + b"\x00" * 99
        )
    assert raised.value.http_status == 415
    assert storage.objects == {}
    assert await count(db_session, HomeworkFile) == 0


async def test_file_over_10_mb_is_413(
    service: FileService, db_session: AsyncSession, homework: Homework, anya: User
) -> None:
    row = await assign(db_session, homework, anya)
    with pytest.raises(AppError) as raised:
        await service.upload_solution(actor(anya), row.id, "big.pdf", PDF + b"0" * MAX_FILE_BYTES)
    assert raised.value.http_status == 413


async def test_eleventh_solution_file_is_rejected(
    service: FileService,
    storage: FakeStorage,
    db_session: AsyncSession,
    homework: Homework,
    anya: User,
) -> None:
    row = await assign(db_session, homework, anya)
    for index in range(MAX_SOLUTION_FILES):
        await service.upload_solution(actor(anya), row.id, f"{index}.pdf", PDF)
    with pytest.raises(BusinessRuleError) as raised:
        await service.upload_solution(actor(anya), row.id, "11.pdf", PDF)
    assert raised.value.code == "files_limit"
    assert len(storage.objects) == MAX_SOLUTION_FILES


async def test_review_files_do_not_count_toward_student_limit(
    service: FileService, db_session: AsyncSession, homework: Homework, anya: User, owner: User
) -> None:
    row = await assign(db_session, homework, anya)
    for index in range(MAX_SOLUTION_FILES):
        await service.upload_solution(actor(anya), row.id, f"{index}.pdf", PDF)
    review = await service.upload_review(actor(owner), row.id, "проверка.pdf", PDF)
    assert review.role == HomeworkFileRole.TEACHER_REVIEW


# ---------------------------------------------------------------- права и состояния


async def test_other_students_assignment_is_404(
    service: FileService, db_session: AsyncSession, homework: Homework, anya: User, boris: User
) -> None:
    row = await assign(db_session, homework, anya)
    with pytest.raises(NotFoundError) as raised:
        await service.upload_solution(actor(boris), row.id, "a.pdf", PDF)
    assert raised.value.code == "assignment_not_found"
    with pytest.raises(NotFoundError):
        await service.upload_solution(actor(boris), 999_999_999, "a.pdf", PDF)


async def test_staff_cannot_upload_student_solutions(
    service: FileService, db_session: AsyncSession, homework: Homework, anya: User, owner: User
) -> None:
    row = await assign(db_session, homework, anya)
    with pytest.raises(PermissionDeniedError):
        await service.upload_solution(actor(owner), row.id, "a.pdf", PDF)


async def test_student_cannot_upload_review_or_material(
    service: FileService, db_session: AsyncSession, homework: Homework, anya: User
) -> None:
    row = await assign(db_session, homework, anya)
    with pytest.raises(PermissionDeniedError):
        await service.upload_review(actor(anya), row.id, "a.pdf", PDF)
    with pytest.raises(PermissionDeniedError):
        await service.upload_material(actor(anya), homework.id, "a.pdf", PDF)


@pytest.mark.parametrize(
    "status", [AssignmentStatus.GRADED, AssignmentStatus.EXPIRED, AssignmentStatus.SUBMITTED]
)
async def test_files_cannot_change_after_review_or_expiry(
    service: FileService,
    db_session: AsyncSession,
    homework: Homework,
    anya: User,
    status: AssignmentStatus,
) -> None:
    row = await assign(db_session, homework, anya, status)
    with pytest.raises(BusinessRuleError) as raised:
        await service.upload_solution(actor(anya), row.id, "a.pdf", PDF)
    assert raised.value.code == "assignment_not_editable"


async def test_needs_revision_allows_new_files(
    service: FileService, db_session: AsyncSession, homework: Homework, anya: User
) -> None:
    row = await assign(db_session, homework, anya, AssignmentStatus.NEEDS_REVISION)
    assert (await service.upload_solution(actor(anya), row.id, "a.pdf", PDF)).id


# ---------------------------------------------------------------- материалы


async def test_staff_uploads_material_and_student_with_assignment_reads_it(
    service: FileService,
    storage: FakeStorage,
    db_session: AsyncSession,
    homework: Homework,
    anya: User,
    boris: User,
    manager: User,
) -> None:
    await assign(db_session, homework, anya)
    material = await service.upload_material(actor(manager), homework.id, "задачи.pdf", PDF)
    (key,) = storage.objects
    assert key.startswith(f"materials/{homework.id}/")
    assert (await db_session.get(HomeworkMaterial, material.id)) is not None
    url = await service.material_url(actor(anya), material.id)
    assert url.expires_in == 600
    assert url.url.startswith(f"https://files.example/{key}")
    with pytest.raises(NotFoundError):
        await service.material_url(actor(boris), material.id)
    assert (await service.material_url(actor(manager), material.id)).url


async def test_material_for_missing_homework_is_404(service: FileService, owner: User) -> None:
    with pytest.raises(NotFoundError) as raised:
        await service.upload_material(actor(owner), 999_999_999, "a.pdf", PDF)
    assert raised.value.code == "homework_not_found"


# ---------------------------------------------------------------- ссылки и удаление


async def test_presigned_url_only_for_owner_of_file_and_staff(
    service: FileService,
    storage: FakeStorage,
    db_session: AsyncSession,
    homework: Homework,
    anya: User,
    boris: User,
    manager: User,
    owner: User,
) -> None:
    row = await assign(db_session, homework, anya)
    item = await service.upload_solution(actor(anya), row.id, "a.pdf", PDF)
    own = await service.file_url(actor(anya), item.id)
    assert own.expires_in == 600
    assert storage.signed[-1][1] == 600
    assert (await service.file_url(actor(manager), item.id)).url
    assert (await service.file_url(actor(owner), item.id)).url
    with pytest.raises(NotFoundError) as foreign:
        await service.file_url(actor(boris), item.id)
    with pytest.raises(NotFoundError) as missing:
        await service.file_url(actor(boris), 999_999_999)
    assert foreign.value.code == missing.value.code == "file_not_found"


async def test_student_can_read_review_file_of_own_assignment(
    service: FileService, db_session: AsyncSession, homework: Homework, anya: User, owner: User
) -> None:
    row = await assign(db_session, homework, anya)
    review = await service.upload_review(actor(owner), row.id, "правки.pdf", PDF)
    assert (await service.file_url(actor(anya), review.id)).url


async def test_student_deletes_own_file_from_db_and_storage(
    service: FileService,
    storage: FakeStorage,
    db_session: AsyncSession,
    homework: Homework,
    anya: User,
) -> None:
    row = await assign(db_session, homework, anya)
    item = await service.upload_solution(actor(anya), row.id, "a.pdf", PDF)
    (key,) = storage.objects
    await service.delete_solution(actor(anya), row.id, item.id)
    assert await count(db_session, HomeworkFile) == 0
    assert storage.deleted == [key]
    assert storage.objects == {}


async def test_delete_rules(
    service: FileService,
    db_session: AsyncSession,
    homework: Homework,
    anya: User,
    boris: User,
    owner: User,
) -> None:
    anya_row = await assign(db_session, homework, anya)
    boris_row = await assign(db_session, homework, boris)
    item = await service.upload_solution(actor(anya), anya_row.id, "a.pdf", PDF)
    review = await service.upload_review(actor(owner), anya_row.id, "r.pdf", PDF)
    with pytest.raises(NotFoundError):  # чужая выдача
        await service.delete_solution(actor(boris), anya_row.id, item.id)
    with pytest.raises(NotFoundError):  # файл из другой выдачи
        await service.delete_solution(actor(boris), boris_row.id, item.id)
    with pytest.raises(NotFoundError):  # файл проверки ученик удалить не может
        await service.delete_solution(actor(anya), anya_row.id, review.id)
    with pytest.raises(PermissionDeniedError):
        await service.delete_solution(actor(owner), anya_row.id, item.id)
    anya_row.status = AssignmentStatus.GRADED
    await db_session.commit()
    with pytest.raises(BusinessRuleError):
        await service.delete_solution(actor(anya), anya_row.id, item.id)
    assert await count(db_session, HomeworkFile) == 2


async def test_storage_is_cleaned_when_db_write_fails(
    service: FileService,
    storage: FakeStorage,
    db_session: AsyncSession,
    homework: Homework,
    anya: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = await assign(db_session, homework, anya)

    async def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("db is down")

    monkeypatch.setattr(service._files, "add", boom)  # noqa: SLF001 - имитация сбоя БД
    with pytest.raises(RuntimeError):
        await service.upload_solution(actor(anya), row.id, "a.pdf", PDF)
    assert storage.objects == {}
    assert len(storage.deleted) == 1
