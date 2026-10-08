"""homework fk indexes

Индексы по внешним ключам, по которым экраны ДЗ выбирают строки (аудит 2026-10-08, п. 9):
файлы и журнал переносов — по выдаче, материалы — по заданию.

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-10-08 00:00:00.000000+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "e6f7a8b9c0d1"
down_revision: str | None = "d5e6f7a8b9c0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Прямое применение миграции."""
    op.create_index("ix_homework_files_assignment_id", "homework_files", ["assignment_id"])
    op.create_index(
        "ix_homework_extensions_assignment_id", "homework_extensions", ["assignment_id"]
    )
    op.create_index("ix_homework_materials_homework_id", "homework_materials", ["homework_id"])


def downgrade() -> None:
    """Откат миграции."""
    op.drop_index("ix_homework_materials_homework_id", table_name="homework_materials")
    op.drop_index("ix_homework_extensions_assignment_id", table_name="homework_extensions")
    op.drop_index("ix_homework_files_assignment_id", table_name="homework_files")
