"""Схемы сотрудников (T2.03): допустимые роли, пустое изменение, privacy-контракт."""

import pytest
from pydantic import ValidationError
from src.core.enums import UserRole
from src.schemas.roles import is_finance_field
from src.schemas.staff import StaffCreate, StaffItem, StaffUpdate


def test_create_defaults_to_manager() -> None:
    staff = StaffCreate(display_name=" Мария ")
    assert staff.display_name == "Мария"
    assert staff.role == UserRole.MANAGER
    assert staff.timezone == "Europe/Moscow"


def test_student_role_is_not_allowed_for_staff() -> None:
    with pytest.raises(ValidationError):
        StaffCreate.model_validate({"display_name": "X", "role": "student"})
    with pytest.raises(ValidationError):
        StaffUpdate.model_validate({"role": UserRole.STUDENT})


def test_update_requires_a_field_and_forbids_null_and_extra() -> None:
    with pytest.raises(ValidationError):
        StaffUpdate()
    with pytest.raises(ValidationError):
        StaffUpdate.model_validate({"role": None})
    with pytest.raises(ValidationError):
        StaffUpdate.model_validate({"display_name": None})
    with pytest.raises(ValidationError):
        StaffUpdate.model_validate({"display_name": "X", "is_active": False})
    assert StaffUpdate(role=UserRole.OWNER).model_fields_set == {"role"}


def test_staff_item_has_no_money_fields() -> None:
    assert not [n for n in StaffItem.model_json_schema()["properties"] if is_finance_field(n)]
