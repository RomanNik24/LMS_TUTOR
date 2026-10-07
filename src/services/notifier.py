"""Интерфейс отправки уведомлений ``Notifier`` (T5.02, docs/03 §8, docs/05 §6).

Сервисы знают только этот интерфейс и не знают, чем отправляется сообщение: транспорт
(Telegram) подключается снаружи, поэтому слой сервисов не зависит от библиотеки бота и
тестируется подменой. Реализация транспорта обязана переводить сбои в три сигнала:

- ``NotifierBlockedError`` — получатель заблокировал бота (повторять бессмысленно);
- ``NotifierTemporaryError`` — временный сбой (сеть, 5xx, лимит запросов): можно повторить;
- ``NotifierPermanentError`` — отказ без шанса на успех (чат не найден, неверный запрос).
"""

from dataclasses import dataclass
from typing import Protocol

from src.core.exceptions import ExternalServiceError


@dataclass(frozen=True, slots=True)
class MessageButton:
    """Инлайн-кнопка под сообщением: ссылка или Mini App (``web_app``)."""

    text: str
    url: str
    web_app: bool = False


@dataclass(frozen=True, slots=True)
class OutgoingMessage:
    """Готовое к отправке сообщение: обычный текст (без разметки) и кнопки по рядам."""

    text: str
    buttons: tuple[tuple[MessageButton, ...], ...] = ()


class NotifierError(ExternalServiceError):
    """Базовая ошибка отправки уведомления."""


class NotifierBlockedError(NotifierError):
    """Получатель заблокировал бота или недоступен для писем бота."""


class NotifierTemporaryError(NotifierError):
    """Временный сбой отправки.

    Attributes:
        retry_after: Сколько секунд просит подождать транспорт (``None`` — не просил).
    """

    def __init__(self, message: str, *, retry_after: int | None = None) -> None:
        """Создать ошибку с необязательной паузой, которую потребовал транспорт."""
        super().__init__(message)
        self.retry_after = retry_after


class NotifierPermanentError(NotifierError):
    """Окончательный отказ: повтор не поможет."""


class Notifier(Protocol):
    """Отправка одного сообщения получателю по его Telegram ID."""

    async def send(self, telegram_id: int, message: OutgoingMessage) -> None:
        """Отправить сообщение.

        Raises:
            NotifierBlockedError: Получатель заблокировал бота.
            NotifierTemporaryError: Временный сбой, можно повторить.
            NotifierPermanentError: Окончательный отказ.
        """
        ...
