"""Константы ядра приложения.

Значения, которые используются в нескольких модулях, вынесены сюда,
чтобы в коде не было «магических» строк (docs/06, раздел A1).
"""

# Имя локального файла с переменными окружения. Реальные секреты хранятся
# только в этом файле, и он не попадает в Git.
ENV_FILE_NAME = ".env.local"

# Заголовок с идентификатором запроса (docs/03: trace/request id).
REQUEST_ID_HEADER = "X-Request-ID"

# Окружения из docs/02, раздел 5.
APP_ENV_LOCAL = "local"
APP_ENV_STAGING = "staging"
APP_ENV_PROD = "prod"

# Допустимые значения APP_ENV (проверяются в Settings).
APP_ENVIRONMENTS: tuple[str, ...] = (APP_ENV_LOCAL, APP_ENV_STAGING, APP_ENV_PROD)

# Режимы работы Telegram-бота (docs/02 §2.2): polling локально, webhook на сервере.
BOT_MODE_POLLING = "polling"
BOT_MODE_WEBHOOK = "webhook"

# Допустимые значения BOT_MODE (проверяются в Settings).
BOT_MODES: tuple[str, ...] = (BOT_MODE_POLLING, BOT_MODE_WEBHOOK)

# Значения по умолчанию для необязательных настроек (docs/02 §7).
S3_REGION_DEFAULT = "us-east-1"
SCHEDULE_HORIZON_WEEKS_DEFAULT = 2

# Статус успешного ответа `GET /health`.
HEALTH_STATUS_OK = "ok"

# Минимальная длина SESSION_SECRET в байтах (требование задачи T1.01).
SECRET_MIN_BYTES = 32

# Telegram WebApp initData: максимальный возраст auth_date (docs/09 §2.2) и
# допустимое расхождение часов для auth_date «из будущего».
INIT_DATA_MAX_AGE_SECONDS = 24 * 60 * 60
INIT_DATA_FUTURE_TOLERANCE_SECONDS = 60
# Размер случайного токена в байтах для secrets.token_urlsafe (256 бит, docs/09 §2.1).
TOKEN_BYTES = 32
