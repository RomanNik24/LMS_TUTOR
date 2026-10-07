"""Тексты уведомлений и вспомогательные правила (T5.03, docs/05 §6)."""

from datetime import UTC, datetime, timedelta

import pytest
from src.core.enums import NotificationType, UserRole
from src.core.exceptions import ValidationError
from src.db.models import Notification, User
from src.services.notification_dispatch import quiet_hours_end
from src.services.notification_render import NotificationRenderer
from src.services.notifications import is_urgent_lesson_change
from src.services.notifier import OutgoingMessage

BASE = "https://lms.example.com"
# 14 октября 2030, 14:00 UTC = 17:00 по Москве
START = datetime(2030, 10, 14, 14, 0, tzinfo=UTC)
EPOCH = int(START.timestamp())


def user(role: UserRole = UserRole.STUDENT, zone: str = "Europe/Moscow") -> User:
    return User(role=role, display_name="Аня", telegram_id=5, timezone=zone)


def note(kind: NotificationType, **payload: object) -> Notification:
    return Notification(user_id=1, type=kind.value, payload=payload, dedup_key="k")


def render(
    kind: NotificationType, who: User | None = None, base: str = BASE, **payload: object
) -> OutgoingMessage:
    return NotificationRenderer(base).render(note(kind, **payload), who or user())


def test_lesson_reminder_local_time_and_links() -> None:
    message = render(
        NotificationType.LESSON_REMINDER,
        lesson_id=1,
        start_epoch=EPOCH,
        subject="Информатика",
        video_url="https://telemost.example/x",
        board_url=None,
    )
    assert message.text == "⏰ Через 30 минут урок: Информатика, пн, 14 окт, 17:00."
    (row,) = message.buttons
    assert [button.url for button in row] == ["https://telemost.example/x"]
    assert row[0].web_app is False


def test_time_is_shown_in_recipient_timezone() -> None:
    message = render(
        NotificationType.LESSON_CANCELLED,
        user(zone="Asia/Yekaterinburg"),
        lesson_id=1,
        start_epoch=EPOCH,
        subject="Информатика",
    )
    assert message.text == "❌ Урок пн, 14 окт, 19:00 отменён."


def test_student_homework_notifications_link_to_card() -> None:
    graded = render(
        NotificationType.HOMEWORK_GRADED, assignment_id=7, title="Графы", score=11, max_score=13
    )
    assert graded.text == "✅ ДЗ «Графы» проверено: 11/13."
    button = graded.buttons[0][0]
    assert button.url == f"{BASE}/app/homework/7"
    assert button.web_app is True
    returned = render(
        NotificationType.HOMEWORK_RETURNED, assignment_id=7, title="Графы", comment="№3"
    )
    assert returned.text == "↩ ДЗ «Графы» нужно доработать. Комментарий: №3"
    assigned = render(
        NotificationType.HOMEWORK_ASSIGNED, assignment_id=7, title="Графы", due_epoch=EPOCH
    )
    assert assigned.text == "📝 Новое ДЗ: «Графы». Срок: пн, 14 окт, 17:00."
    deadline = render(
        NotificationType.HOMEWORK_DEADLINE, assignment_id=7, due_epoch=EPOCH, title="Графы"
    )
    assert deadline.text == "📌 Завтра дедлайн ДЗ «Графы». Не забудь сдать."


def test_staff_notifications_link_to_review_and_admin() -> None:
    staff = user(UserRole.MANAGER)
    submitted = render(
        NotificationType.HOMEWORK_SUBMITTED,
        staff,
        assignment_id=7,
        title="Графы",
        student_name="Аня",
    )
    assert submitted.text == "📥 Сдано ДЗ «Графы»: Аня."
    assert submitted.buttons[0][0].url == f"{BASE}/admin/assignments/7"
    joined = render(NotificationType.STUDENT_JOINED, staff, student_id=3, student_name="Борис")
    assert joined.buttons[0][0].url == f"{BASE}/admin/"
    digest = render(NotificationType.MORNING_DIGEST, staff, lines=["Уроки:", "17:00 Аня"])
    assert digest.text == "Уроки:\n17:00 Аня"
    rescheduled = render(
        NotificationType.LESSON_RESCHEDULED,
        lesson_id=1,
        old_start_epoch=EPOCH,
        new_start_epoch=EPOCH + 86400,
        subject="Информатика",
    )
    assert rescheduled.text == "🔁 Урок перенесён: было пн, 14 окт, 17:00, стало вт, 15 окт, 17:00."


def test_no_https_base_means_no_buttons() -> None:
    message = render(
        NotificationType.HOMEWORK_GRADED,
        base="http://localhost",
        assignment_id=7,
        title="Графы",
        score=1,
        max_score=2,
    )
    assert message.buttons == ()


@pytest.mark.parametrize(
    ("kind", "payload"),
    [
        (NotificationType.HOMEWORK_GRADED, {"assignment_id": 1, "title": "x"}),
        (
            NotificationType.LESSON_CANCELLED,
            {"lesson_id": 1, "start_epoch": "soon", "subject": "x"},
        ),
        (NotificationType.MORNING_DIGEST, {"lines": "not a list"}),
        (NotificationType.LESSON_REMINDER, {"lesson_id": 1, "start_epoch": True, "subject": "x"}),
    ],
)
def test_bad_payload_is_rejected(kind: NotificationType, payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError) as caught:
        NotificationRenderer(BASE).render(note(kind, **payload), user())
    assert caught.value.code == "bad_notification_payload"


def test_unknown_type_is_rejected() -> None:
    row = Notification(user_id=1, type="mystery", payload={}, dedup_key="k")
    with pytest.raises(ValidationError):
        NotificationRenderer(BASE).render(row, user())


@pytest.mark.parametrize(
    ("utc_hour", "utc_minute", "expected"),
    [
        (18, 59, None),  # 21:59 по Москве
        (19, 0, datetime(2030, 10, 15, 5, 0, tzinfo=UTC)),  # 22:00 -> 08:00 завтра
        (20, 0, datetime(2030, 10, 15, 5, 0, tzinfo=UTC)),  # 23:00
        (2, 0, datetime(2030, 10, 14, 5, 0, tzinfo=UTC)),  # 05:00 -> 08:00 сегодня
        (4, 59, datetime(2030, 10, 14, 5, 0, tzinfo=UTC)),  # 07:59
        (5, 0, None),  # ровно 08:00 тихие часы закончились
    ],
)
def test_quiet_hours_boundaries(utc_hour: int, utc_minute: int, expected: datetime | None) -> None:
    now = datetime(2030, 10, 14, utc_hour, utc_minute, tzinfo=UTC)
    assert quiet_hours_end(now, "Europe/Moscow") == expected


def test_quiet_hours_follow_recipient_timezone() -> None:
    now = datetime(2030, 10, 14, 19, 0, tzinfo=UTC)  # 22:00 Москва
    assert quiet_hours_end(now, "Europe/Moscow") == datetime(2030, 10, 15, 5, 0, tzinfo=UTC)
    # Екатеринбург (UTC+5): 00:00 15 октября, ждать до 08:00 того же дня
    assert quiet_hours_end(now, "Asia/Yekaterinburg") == datetime(2030, 10, 15, 3, 0, tzinfo=UTC)
    # Владивосток (UTC+10): 05:00 15 октября, ждать до 08:00 того же дня
    assert quiet_hours_end(now, "Asia/Vladivostok") == datetime(2030, 10, 14, 22, 0, tzinfo=UTC)
    # Калининград (UTC+2): 21:00 — тихие часы ещё не начались
    assert quiet_hours_end(now, "Europe/Kaliningrad") is None


def test_lesson_change_is_urgent_within_12_hours() -> None:
    now = datetime(2030, 10, 14, 12, 0, tzinfo=UTC)
    assert is_urgent_lesson_change(now, now + timedelta(hours=11, minutes=59)) is True
    assert is_urgent_lesson_change(now, now + timedelta(hours=12)) is True
    assert is_urgent_lesson_change(now, now + timedelta(hours=12, minutes=1)) is False
    # перенос: срочно, если старое ИЛИ новое время ближе 12 часов
    far = now + timedelta(days=3)
    assert is_urgent_lesson_change(now, far, now + timedelta(hours=2)) is True
    assert is_urgent_lesson_change(now, far, far + timedelta(days=1)) is False
