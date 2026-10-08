"""Единые заголовки безопасности ответов API (T8.08, docs/09).

Nginx добавляет такие же заголовки статике и (через ``proxy_hide_header``) заменяет ими заголовки
backend, так что в браузер приходит один набор. Если API открыт напрямую (порт 8000 на
localhost, тесты, отладка), заголовки ставит само приложение.

* ``X-Content-Type-Options: nosniff`` — браузер не угадывает тип содержимого;
* ``Referrer-Policy: no-referrer`` — адреса страниц (в них бывают токены) не уходят дальше;
* ``Cache-Control: no-store`` — ответы ``/api`` содержат персональные данные и не кэшируются
  (если обработчик не задал своё значение).
"""

from collections.abc import Awaitable, Callable

from starlette.requests import Request
from starlette.responses import Response

from src.core.constants import API_V1_PREFIX

SECURITY_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}
NO_STORE = "no-store"


async def security_headers_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Дописать заголовки безопасности к любому ответу."""
    response = await call_next(request)
    for name, value in SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    if request.url.path.startswith(API_V1_PREFIX):
        response.headers.setdefault("Cache-Control", NO_STORE)
    return response
