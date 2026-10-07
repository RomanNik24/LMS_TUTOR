"""Тексты уведомлений по типам (T5.03, docs/05 §6): ``payload`` + получатель → сообщение.

Контракт полей ``payload`` (его заполняют события в сервисах, T5.06):

| тип                  | поля                                                                  |
|----------------------|-----------------------------------------------------------------------|
| ``lesson_reminder``  | ``lesson_id``, ``start_epoch``, ``subject``, ``video_url``, ``board_url`` |
| ``homework_deadline``| ``assignment_id``, ``due_epoch``, ``title``                           |
| ``homework_graded``  | ``assignment_id``, ``title``, ``score``, ``max_score``                |
| ``homework_returned``| ``assignment_id``, ``title``, ``comment``                             |
| ``homework_assigned``| ``assignment_id``, ``title``, ``due_epoch``                           |
| ``lesson_cancelled`` | ``lesson_id``, ``start_epoch``, ``subject``                           |
| ``lesson_rescheduled``| ``lesson_id``, ``old_start_epoch``, ``new_start_epoch``, ``subject`` |
| ``homework_submitted``/``homework_expired`` | ``assignment_id``, ``title``, ``student_name`` |
| ``lesson_unmarked``  | ``lesson_id``, ``start_epoch``, ``subject``                           |
| ``morning_digest``   | ``lines`` (готовые строки сводки)                                     |
| ``student_joined``   | ``student_id``, ``student_name``                                      |

Время (``*_epoch``) хранится в UTC и показывается в поясе получателя. Ссылки-кнопки ведут в
Mini App (только по HTTPS, docs/05 §5.3); без HTTPS-адреса кнопка приложения не добавляется.
"""

from datetime import UTC, datetime

from src.core import texts
from src.core.enums import NotificationType, UserRole
from src.core.exceptions import ValidationError
from src.core.timeutils import to_local
from src.db.models import Notification, User
from src.services.notifier import MessageButton, OutgoingMessage

BAD_PAYLOAD = "bad_notification_payload"


def _bad(reason: str) -> ValidationError:
    return ValidationError(f"Некорректные данные уведомления: {reason}", code=BAD_PAYLOAD)


def _text(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise _bad(key)
    return value


def _number(payload: dict[str, object], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise _bad(key)
    return value


def _optional_text(payload: dict[str, object], key: str) -> str | None:
    value = payload.get(key)
    return value if isinstance(value, str) and value else None


def _lines(payload: dict[str, object]) -> list[str]:
    value = payload.get("lines")
    if not isinstance(value, list) or not all(isinstance(line, str) for line in value):
        raise _bad("lines")
    return [line for line in value if isinstance(line, str)]


class NotificationRenderer:
    """Собирает ``OutgoingMessage`` для уведомления."""

    def __init__(self, public_base_url: str) -> None:
        """Создать рендерер.

        Args:
            public_base_url: Публичный адрес приложения (``PUBLIC_BASE_URL``).
        """
        base = public_base_url.strip().rstrip("/")
        self._base = base if base.startswith("https://") else None

    def render(self, notification: Notification, user: User) -> OutgoingMessage:
        """Сообщение для получателя.

        Raises:
            ValidationError: ``bad_notification_payload`` — неизвестный тип или битые данные.
        """
        data = notification.payload
        zone = user.timezone

        def when(epoch_key: str) -> str:
            moment = datetime.fromtimestamp(_number(data, epoch_key), tz=UTC)
            return texts.local_when(to_local(moment, zone))

        try:
            kind = NotificationType(notification.type)
        except ValueError as error:
            raise _bad("type") from error

        match kind:
            case NotificationType.LESSON_REMINDER:
                message = texts.NOTIFY_LESSON_REMINDER.format(
                    subject=_text(data, "subject"), time=when("start_epoch")
                )
                return OutgoingMessage(message, self._lesson_links(data))
            case NotificationType.HOMEWORK_DEADLINE:
                return self._homework(
                    user, data, texts.NOTIFY_HOMEWORK_DEADLINE.format(title=_text(data, "title"))
                )
            case NotificationType.HOMEWORK_GRADED:
                return self._homework(
                    user,
                    data,
                    texts.NOTIFY_HOMEWORK_GRADED.format(
                        title=_text(data, "title"),
                        score=_number(data, "score"),
                        max_score=_number(data, "max_score"),
                    ),
                )
            case NotificationType.HOMEWORK_RETURNED:
                return self._homework(
                    user,
                    data,
                    texts.NOTIFY_HOMEWORK_RETURNED.format(
                        title=_text(data, "title"), comment=_text(data, "comment")
                    ),
                )
            case NotificationType.HOMEWORK_ASSIGNED:
                return self._homework(
                    user,
                    data,
                    texts.NOTIFY_HOMEWORK_ASSIGNED.format(
                        title=_text(data, "title"), due=when("due_epoch")
                    ),
                )
            case NotificationType.LESSON_CANCELLED:
                return self._plain(
                    user, texts.NOTIFY_LESSON_CANCELLED.format(when=when("start_epoch"))
                )
            case NotificationType.LESSON_RESCHEDULED:
                return self._plain(
                    user,
                    texts.NOTIFY_LESSON_RESCHEDULED.format(
                        old=when("old_start_epoch"), new=when("new_start_epoch")
                    ),
                )
            case NotificationType.HOMEWORK_SUBMITTED:
                return self._homework(
                    user,
                    data,
                    texts.NOTIFY_HOMEWORK_SUBMITTED.format(
                        title=_text(data, "title"), student=_text(data, "student_name")
                    ),
                )
            case NotificationType.HOMEWORK_EXPIRED:
                return self._homework(
                    user,
                    data,
                    texts.NOTIFY_HOMEWORK_EXPIRED.format(
                        title=_text(data, "title"), student=_text(data, "student_name")
                    ),
                )
            case NotificationType.LESSON_UNMARKED:
                return self._plain(
                    user,
                    texts.NOTIFY_LESSON_UNMARKED.format(
                        subject=_text(data, "subject"), when=when("start_epoch")
                    ),
                )
            case NotificationType.MORNING_DIGEST:
                return self._plain(user, "\n".join(_lines(data)))
            case NotificationType.STUDENT_JOINED:
                return self._plain(
                    user, texts.NOTIFY_STUDENT_JOINED.format(student=_text(data, "student_name"))
                )

    # ------------------------------------------------------------------ кнопки

    def _is_staff(self, user: User) -> bool:
        return user.role != UserRole.STUDENT

    def _plain(self, user: User, text: str) -> OutgoingMessage:
        """Сообщение с одной кнопкой «Открыть приложение» (если есть HTTPS-адрес)."""
        if self._base is None:
            return OutgoingMessage(text)
        path = "/admin/" if self._is_staff(user) else "/app/"
        label = (
            texts.NOTIFY_BUTTON_OPEN_ADMIN if self._is_staff(user) else texts.NOTIFY_BUTTON_OPEN_APP
        )
        return OutgoingMessage(text, ((MessageButton(label, self._base + path, web_app=True),),))

    def _homework(self, user: User, data: dict[str, object], text: str) -> OutgoingMessage:
        """Сообщение с кнопкой «Открыть ДЗ» (ученику — его карточка, персоналу — проверка)."""
        if self._base is None:
            return OutgoingMessage(text)
        assignment_id = _number(data, "assignment_id")
        if self._is_staff(user):
            url = f"{self._base}/admin/assignments/{assignment_id}"
        else:
            url = f"{self._base}/app/homework/{assignment_id}"
        return OutgoingMessage(
            text, ((MessageButton(texts.NOTIFY_BUTTON_OPEN_HOMEWORK, url, web_app=True),),)
        )

    @staticmethod
    def _lesson_links(data: dict[str, object]) -> tuple[tuple[MessageButton, ...], ...]:
        """Кнопки «Телемост» и «Доска» из ссылок урока (обычные ссылки, не Mini App)."""
        row: list[MessageButton] = []
        video = _optional_text(data, "video_url")
        board = _optional_text(data, "board_url")
        if video is not None:
            row.append(MessageButton(texts.BOT_LINK_VIDEO, video))
        if board is not None:
            row.append(MessageButton(texts.BOT_LINK_BOARD, board))
        return (tuple(row),) if row else ()
