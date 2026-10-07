"""Защита от возврата ошибки 502 после пересборки: nginx должен заново искать контейнер app."""

import re
from pathlib import Path

NGINX = Path(__file__).resolve().parents[2] / "nginx"


def test_backend_address_is_resolved_per_request() -> None:
    """Статический ``proxy_pass http://app:8000`` разрешает имя один раз при старте nginx.

    После ``docker compose up -d --build`` у контейнера app новый IP, и такой nginx отвечает 502,
    пока его не перезапустить. Поэтому адрес задаётся переменной и есть резолвер Docker.
    """
    snippet = (NGINX / "snippets" / "proxy-app.conf").read_text(encoding="utf-8")
    config = (NGINX / "conf.d" / "default.conf").read_text(encoding="utf-8")
    directives = [
        line.strip() for line in snippet.splitlines() if not line.lstrip().startswith("#")
    ]
    code = "\n".join(directives)
    assert not re.search(r"proxy_pass\s+http://app", code)
    assert "set $app_upstream app:8000;" in code
    assert "proxy_pass http://$app_upstream;" in code
    assert re.search(r"^resolver\s+127\.0\.0\.11\b", config, flags=re.MULTILINE)
