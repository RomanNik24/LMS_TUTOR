"""Архитектурные правила T1.11 без подключения к Telegram/БД."""

import re
from pathlib import Path

from src.bot.commands import commands_for
from src.bot.keyboards import app_url
from src.core.enums import UserRole

ROOT = Path(__file__).resolve().parents[2]


def _sources(folder: str) -> list[Path]:
    return list((ROOT / folder).rglob("*.py"))


def test_services_do_not_import_aiogram() -> None:
    for path in _sources("src/services"):
        assert "aiogram" not in path.read_text(encoding="utf-8"), path.name


def test_no_message_conf_anywhere() -> None:
    for path in _sources("src"):
        assert "message.conf" not in path.read_text(encoding="utf-8"), path.name


def test_only_client_module_creates_bot() -> None:
    """Единственная точка исходящих запросов к Telegram — src/bot/client.py (docs/02 §6)."""
    for path in _sources("src"):
        if path.name == "client.py" and path.parent.name == "bot":
            continue
        text = path.read_text(encoding="utf-8")
        assert "Bot(" not in text.replace("BotRuntime(", ""), path.name
        assert "AiohttpSession" not in text, path.name


def test_user_facing_bot_modules_have_no_russian_literals() -> None:
    """Хэндлеры, клавиатуры и команды не содержат русских литералов: тексты в texts.py."""
    cyrillic = re.compile(r"""["'][^"'\n]*[А-Яа-яЁё][^"'\n]*["']""")
    files = [
        *_sources("src/bot/handlers"),
        ROOT / "src/bot/keyboards.py",
        ROOT / "src/bot/commands.py",
    ]
    for path in files:
        code = re.sub(r'""".*?"""', "", path.read_text(encoding="utf-8"), flags=re.S)
        code = "\n".join(line for line in code.splitlines() if not line.lstrip().startswith("#"))
        assert not cyrillic.search(code), path.name


def test_commands_by_state() -> None:
    assert [c.command for c in commands_for(None)] == ["start", "help"]
    for role in (UserRole.STUDENT, UserRole.MANAGER, UserRole.OWNER):
        assert [c.command for c in commands_for(role)] == [
            "start",
            "app",
            "web",
            "logout",
            "help",
        ]


def test_app_url_requires_https() -> None:
    assert app_url("https://x.example/", UserRole.STUDENT) == "https://x.example/app/"
    assert app_url("https://x.example", UserRole.OWNER) == "https://x.example/admin/"
    assert app_url("http://127.0.0.1:8000", UserRole.STUDENT) is None
    assert app_url("", UserRole.STUDENT) is None
