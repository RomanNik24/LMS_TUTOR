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
    """В репозитории T1.03 существует ровно одна revision head."""

    config = Config(str(ALEMBIC_INI))
    script = ScriptDirectory.from_config(config)

    assert script.get_heads() == ["fddb2f6cef06"]

    revision = script.get_revision("fddb2f6cef06")
    assert revision is not None
    assert revision.down_revision is None
