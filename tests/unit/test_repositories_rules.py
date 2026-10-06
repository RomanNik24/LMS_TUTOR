"""Архитектурные правила T1.06 без подключения к БД."""

import dataclasses
import re
from pathlib import Path

import pytest
from src.core.current_user import CurrentUser
from src.core.enums import UserRole

ROOT = Path(__file__).resolve().parents[2]


def _py_files(folder: str) -> list[Path]:
    return [p for p in (ROOT / folder).rglob("*.py")]


def test_repositories_never_call_commit() -> None:
    """В src/repositories нет commit() (docs/03 §6)."""
    for path in _py_files("src/repositories"):
        code = "\n".join(
            line
            for line in path.read_text(encoding="utf-8").splitlines()
            if not line.lstrip().startswith("#")
        )
        # Упоминания в docstring допустимы только словами; вызов — это `commit(`.
        calls = re.findall(r"\.commit\(", code)
        assert not calls, f"{path.name}: найден вызов commit()"


def test_src_has_no_actor_typed_as_orm_user() -> None:
    """Сервисы принимают CurrentUser, а не ORM-модель User (docs/08 §9)."""
    for path in _py_files("src"):
        assert "actor: User" not in path.read_text(encoding="utf-8"), path.name


def test_current_user_is_frozen() -> None:
    """CurrentUser неизменяем и несёт id, role, timezone."""
    user = CurrentUser(id=1, role=UserRole.OWNER, timezone="Europe/Moscow")
    assert [f.name for f in dataclasses.fields(user)] == ["id", "role", "timezone"]
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(user, "id", 2)  # noqa: B010 - проверка frozen без нарушения типизации
