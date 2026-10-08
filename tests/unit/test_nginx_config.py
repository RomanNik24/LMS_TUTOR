"""Конфигурация nginx: адрес backend на каждый запрос, CSP для фото из хранилища."""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
NGINX = ROOT / "nginx"


def test_csp_allows_images_from_public_s3_endpoint() -> None:
    """Регрессия аудита 2026-10-08, п. 3: фото ДЗ идут по подписанной ссылке S3 (другой origin).

    С ``img-src 'self' data:`` браузер блокировал их на экране проверки. Адрес берётся из
    ``S3_PUBLIC_ENDPOINT`` — того же, от которого app строит подписанные ссылки.
    """
    template = NGINX / "templates" / "snippets" / "security-headers.conf.template"
    csp = re.search(r'Content-Security-Policy "([^"]+)"', template.read_text(encoding="utf-8"))
    assert csp is not None
    img_src = next(d.strip() for d in csp.group(1).split(";") if d.strip().startswith("img-src"))
    assert img_src == "img-src 'self' data: ${S3_PUBLIC_ENDPOINT}"
    assert not (NGINX / "snippets" / "security-headers.conf").exists()  # только шаблон

    dockerfile = (ROOT / "frontend" / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY nginx/templates/ /etc/nginx/templates/" in dockerfile
    assert "NGINX_ENVSUBST_OUTPUT_DIR=/etc/nginx" in dockerfile

    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    nginx_env = compose["services"]["nginx"]["environment"]
    app_env = compose["services"]["app"]["environment"]
    assert nginx_env["S3_PUBLIC_ENDPOINT"] == app_env["S3_PUBLIC_ENDPOINT"]


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


def test_access_log_hides_login_tokens_and_413_is_json() -> None:
    """Аудит 2026-10-08, пп. 7 и 16: токен входа не попадает в журнал, 413 — JSON docs/08 §1."""
    config = (NGINX / "conf.d" / "default.conf").read_text(encoding="utf-8")
    # по $request_uri, а не по $uri: try_files для маршрутов SPA переводит $uri на /index.html
    assert "map $request_uri $log_uri {" in config
    assert re.search(r'~\^/login/\s+"/login/\*\*\*";', config)
    assert "error_page 413 = @payload_too_large;" in config
    assert '"code":"file_too_large"' in config
