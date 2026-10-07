"""Проверки конфигурации Alembic T1.03."""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = ROOT / "alembic.ini"


def test_alembic_ini_is_ascii_and_uses_project_layout() -> None:
    """alembic.ini читается как ASCII и содержит утверждённые пути."""

    ALEMBIC_INI.read_bytes().decode("ascii")

    config = Config(str(ALEMBIC_INI))

    assert config.get_main_option("script_location") == "src/db/migrations"
    assert config.get_main_option("prepend_sys_path") == "."
    assert config.get_main_option("timezone") == "UTC"


def test_alembic_has_single_head() -> None:
    """В репозитории существует ровно одна revision head (сейчас — T5.01)."""

    config = Config(str(ALEMBIC_INI))
    script = ScriptDirectory.from_config(config)

    assert script.get_heads() == ["d5e6f7a8b9c0"]

    revision = script.get_revision("d5e6f7a8b9c0")
    assert revision is not None
    assert revision.down_revision == "c4d2e5f7a8b9"
    homework = script.get_revision("c4d2e5f7a8b9")
    assert homework is not None
    assert homework.down_revision == "a3b1c0d4e5f6"
    schedule = script.get_revision("a3b1c0d4e5f6")
    assert schedule is not None
    assert schedule.down_revision == "fddb2f6cef06"
    first = script.get_revision("fddb2f6cef06")
    assert first is not None
    assert first.down_revision is None
