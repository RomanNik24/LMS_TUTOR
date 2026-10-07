"""Heartbeat воркера: HTTP-пинг во внешний мониторинг (T5.04, docs/10 §8).

Если от воркера нет пинга, мониторинг (Healthchecks) поднимает тревогу. Сбой пинга сам по себе
не должен ронять воркер: он только пишется в лог.
"""

import logging

import aiohttp

from src.core.constants import HEARTBEAT_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)


async def ping(url: str) -> bool:
    """Отправить GET на адрес мониторинга.

    Args:
        url: Адрес пинга; пустой — ничего не делать.

    Returns:
        ``True``, если мониторинг ответил 2xx; иначе (или при пустом адресе) ``False``.
        Адрес в лог не попадает: в нём бывает секретный идентификатор проверки.
    """
    if not url:
        return False
    timeout = aiohttp.ClientTimeout(total=HEARTBEAT_TIMEOUT_SECONDS)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session, session.get(url) as response:
            if response.status < 300:  # noqa: PLR2004 - граница успешных статусов HTTP
                return True
            logger.warning("Heartbeat: мониторинг ответил статусом %s", response.status)
    except (aiohttp.ClientError, TimeoutError) as error:
        logger.warning("Heartbeat: не удалось отправить пинг (%s)", type(error).__name__)
    return False
