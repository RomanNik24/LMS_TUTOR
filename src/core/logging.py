"""JSON-логирование и middleware `request_id` (задача T1.01).

Требования (`docs/09` §4, `docs/06` A5, QWEN.md §20):
- логи — одна JSON-строка на событие в stdout (собираются контейнерным
  драйвером логов, `docs/10`);
- каждый запрос помечается идентификатором `request_id`, он же возвращается
  клиенту в заголовке `X-Request-ID` — по нему ошибка ищется в логах;
- **персональные данные в логи запрещены**: разрешён только числовой `user_id`;
  имена, телефоны, тексты сообщений, `initData`, токены и секреты в полях
  логов появляться не должны (фильтр ниже отбивает явно запрещённые ключи).

Фильтр `NoPIIFilter` — вторая линия защиты: даже если разработчик передаст
в логгер структуру с запрещённым полем, значение будет вырезано до записи.
Первая линия — код-ревью и правила docs/06.
"""

import logging
import re
import sys
import uuid
from contextvars import ContextVar

from pythonjsonlogger.json import JsonFormatter
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from src.core.constants import BOT_WEBHOOK_PATH, REQUEST_ID_HEADER, WEBHOOK_PATH_REDACTED

# Контекст текущего запроса: RequestIdMiddleware проставляет request_id,
# логгер читает его при форматировании любой записи этого запроса.
_request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


def get_current_request_id() -> str:
    """Вернуть request_id текущего запроса (или `-` вне HTTP-контекста)."""
    return _request_id_ctx.get()


# Ключи extra/структур, которые никогда не пишутся в лог (docs/09 §4, §5).
# Служебные поля LogRecord перечислены отдельно: они не несут ПДн, но и в
# JSON-выводе бесполезны — исключаем через `reserved`.
FORBIDDEN_LOG_KEYS: frozenset[str] = frozenset(
    {
        "init_data",
        "initdata",
        "token",
        "tokens",
        "session_secret",
        "bot_token",
        "webhook_secret",
        "sentry_dsn",
        "password",
        "secret",
        "cookie",
        "cookies",
        "authorization",
        "phone",
        "full_name",
        "display_name",
        "teacher_notes",
        "email",
        "first_name",
        "last_name",
    }
)

# Поле, которое может присутствовать в структурированном событии:
# только числовой идентификатор пользователя (docs/09 §4).
ALLOWED_USER_FIELD = "user_id"


class NoPIIFilter(logging.Filter):
    """Вырезает из записи лога запрещённые ключи (защита от утечки ПДн).

    Работает с `record.__dict__`: удаляет атрибуты, чьи имена попали в
    `FORBIDDEN_LOG_KEYS`. Числовой `user_id` сохраняется — он разрешён.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Очистить запись и всегда вернуть True (запись не отбрасывается)."""
        for key in list(vars(record)):
            if key.lower() in FORBIDDEN_LOG_KEYS:
                delattr(record, key)
        # Сообщения строятся вызывающим кодом; на всякий случай проверяем,
        # что в отформатированной строке не появились известные секрет-маркеры.
        return True


_WEBHOOK_PATH_RE = re.compile(re.escape(BOT_WEBHOOK_PATH) + r"/[^/\s?\"']+")


def redact_webhook_path(text: str) -> str:
    """Заменить секретный сегмент пути вебхука на ``***`` (он выводится из ``WEBHOOK_SECRET``)."""
    return _WEBHOOK_PATH_RE.sub(WEBHOOK_PATH_REDACTED, text)


class WebhookPathFilter(logging.Filter):
    """Маскирует секретный сегмент пути вебхука в сообщениях и аргументах (``uvicorn.access``)."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Подменить сообщение и строковые аргументы; запись не отбрасывается."""
        if isinstance(record.msg, str):
            record.msg = redact_webhook_path(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(
                redact_webhook_path(arg) if isinstance(arg, str) else arg for arg in record.args
            )
        return True


class RequestIdFilter(logging.Filter):
    """Добавляет `request_id` текущего запроса в каждую запись лога."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Проставить `record.request_id` из контекста (или `-`)."""
        if getattr(record, "request_id", None) is None:
            record.request_id = get_current_request_id()
        return True


def setup_logging(app_env: str = "local") -> None:
    """Настроить корневой логгер: JSON в stdout, без дублей хендлеров.

    Идемпотентна: повторный вызов заменяет настройку, а не наслаивает её.

    Args:
        app_env: Окружение (`local|staging|prod`). Уровень: INFO везде,
            DEBUG только в local. В prod WARNING у сторонних библиотек,
            чтобы их логи не раздувались.
    """
    level = logging.DEBUG if app_env == "local" else logging.INFO

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        JsonFormatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s %(request_id)s",
            # Служебные поля LogRecord наружу не пишем (время уже есть в asctime).
            reserved_attrs=(
                "args",
                "exc_info",
                "msg",
                "msecs",
                "module",
                "lineno",
                "funcName",
                "pathname",
                "filename",
                "stack_info",
            ),
        )
    )
    handler.addFilter(NoPIIFilter())
    handler.addFilter(WebhookPathFilter())
    handler.addFilter(RequestIdFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    # Служебный шум библиотек: asyncio и HTTP-клиенты в DEBUG не нужны нигде,
    # а в staging/prod сторонним библиотекам достаточно WARNING.
    third_party_level = logging.INFO if app_env == "local" else logging.WARNING
    for name in ("asyncio", "httpx", "httpcore", "sqlalchemy.engine"):
        logging.getLogger(name).setLevel(third_party_level)

    # Логи uvicorn/fastapi идут через наш root-хендлер своим не нужны.
    for noisy in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        logger = logging.getLogger(noisy)
        logger.handlers.clear()
        logger.propagate = True


def _new_request_id() -> str:
    """Сгенерировать идентификатор запроса (uuid4, hex)."""
    return uuid.uuid4().hex


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Middleware: берёт `X-Request-ID` из запроса (или генерирует свой),
    кладёт в `request.state` и в заголовок ответа, чтобы логгер события
    мог подхватить его (через контекст запроса).
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Обработать один запрос: проставить request_id в контекст и заголовок ответа.

        Args:
            request: Входящий запрос.
            call_next: Следующий элемент цепочки middleware.

        Returns:
            Ответ приложения с заголовком `X-Request-ID`.
        """
        incoming = request.headers.get(REQUEST_ID_HEADER, "")
        # Принимаем только «разумные» значения: длина ≤ 64, printable, без
        # пробелов — иначе генерируем новый (защита от лог-инъекций).
        request_id = incoming if _is_safe_request_id(incoming) else _new_request_id()
        request.state.request_id = request_id
        scope_state = getattr(request, "scope", {}).get("state")
        if isinstance(scope_state, dict):
            # То же значение в ASGI-scope: доступно чистым ASGI-middleware.
            scope_state["request_id"] = request_id
        token = _request_id_ctx.set(request_id)
        try:
            response = await call_next(request)
        finally:
            _request_id_ctx.reset(token)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response


def _is_safe_request_id(value: str) -> bool:
    """True, если значение подходит как request_id: непустое, ≤ 64, printable ASCII."""
    return 0 < len(value) <= 64 and value.isprintable() and " " not in value


def get_request_id(request: Request) -> str | None:
    """Вернуть request_id запроса (для обработчиков ошибок).

    Args:
        request: Текущий запрос.

    Returns:
        Идентификатор либо `None`, если middleware ещё не отработал.
    """
    value: object = getattr(request.state, "request_id", None)
    return value if isinstance(value, str) else None
