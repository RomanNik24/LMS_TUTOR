"""Схемы файлов домашних заданий (docs/08 §6, T4.05)."""

from datetime import datetime

from pydantic import BaseModel

from src.core.enums import HomeworkFileRole


class HomeworkFileItem(BaseModel):
    """Файл выдачи в ответе: без ключа S3 (клиенту он не нужен и раскрывать его незачем)."""

    id: int
    assignment_id: int
    role: HomeworkFileRole
    original_name: str
    content_type: str
    size_bytes: int
    created_at: datetime


class MaterialItem(BaseModel):
    """Материал преподавателя к заданию."""

    id: int
    homework_id: int
    original_name: str
    content_type: str
    size_bytes: int


class FileUrl(BaseModel):
    """Подписанная ссылка на чтение (docs/08 §6)."""

    url: str
    expires_in: int
