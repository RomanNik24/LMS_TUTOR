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
# Подписанная ссылка на файл живёт 10 минут (docs/09: файлы отдаются только по временной ссылке).
S3_PRESIGN_TTL_SECONDS = 600
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

# Серверные сессии (docs/09 §2.3): cookie с идентификатором, данные — в Redis.
SESSION_COOKIE_NAME = "session_id"
SESSION_TTL_STUDENT_SECONDS = 30 * 24 * 60 * 60
SESSION_TTL_STAFF_SECONDS = 7 * 24 * 60 * 60
SESSION_KEY_PREFIX = "session:"
USER_SESSIONS_KEY_PREFIX = "user_sessions:"

# CSRF (docs/09 §2.3.1): изменяющие методы и заголовок-маркер.
CSRF_UNSAFE_METHODS = frozenset({"POST", "PATCH", "PUT", "DELETE"})
CSRF_REQUIRED_HEADER = "x-requested-with"
CSRF_REQUIRED_HEADER_VALUE = "XMLHttpRequest"
# Webhook Telegram защищён секретом, а не Origin (docs/09 §1).
CSRF_EXEMPT_PATH_PREFIXES: tuple[str, ...] = ("/telegram/",)

# Rate limiting (docs/08 §10): окно — одна минута.
RATE_LIMIT_WINDOW_SECONDS = 60
RATE_LIMIT_AUTH_PER_MINUTE = 10
RATE_LIMIT_USER_PER_MINUTE = 120
RATE_LIMIT_KEY_PREFIX = "rate:"
# Загрузка файлов: не больше 30 за 10 минут на пользователя (docs/08 §10).
RATE_LIMIT_UPLOAD_COUNT = 30
RATE_LIMIT_UPLOAD_WINDOW_SECONDS = 600

# CORS включается только локально (docs/09 §2.3.1): dev-сервер Vite на другом порту.
LOCAL_CORS_ORIGINS: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")
# Статусы /health (docs/08 §3).
HEALTH_STATUS_DEGRADED = "degraded"
HEALTH_COMPONENT_OK = "ok"
HEALTH_COMPONENT_ERROR = "error"

# Приглашения и ссылки входа (docs/04 §2.5, docs/09 §2).
INVITE_TTL_DAYS = 7
WEB_LOGIN_TTL_MINUTES = 10
# Неудачные попытки принять приглашение: 5 за 10 минут на telegram_id (docs/08 §10).
INVITE_FAILED_ATTEMPTS_LIMIT = 5
INVITE_FAILED_ATTEMPTS_WINDOW_SECONDS = 10 * 60
INVITE_FAILURE_SCOPE = "invite_fail"

# Список учеников (docs/08 §1 «Пагинация»): лимит по умолчанию и максимум.
LIST_LIMIT_DEFAULT = 50
LIST_LIMIT_MAX = 200
# Часовой пояс нового ученика по умолчанию (docs/04 §2.1).
DEFAULT_USER_TIMEZONE = "Europe/Moscow"
# Длина ссылок профиля ученика (docs/04 §2.2).
PROFILE_URL_MAX_LENGTH = 500

# Базовый путь REST API (docs/08 §1).
API_V1_PREFIX = "/api/v1"

# Бот (docs/05 §4, §7): TTL FSM, допустимые типы апдейтов, префикс приглашения.
BOT_FSM_TTL_SECONDS = 60 * 60
BOT_ALLOWED_UPDATES: tuple[str, ...] = ("message", "callback_query", "my_chat_member")
BOT_INVITE_PAYLOAD_PREFIX = "inv_"
BOT_WEBHOOK_PATH = "/telegram/webhook"
BOT_WEBHOOK_AUTH_HEADER = "x-telegram-bot-api-secret-token"
# Маска секретного сегмента пути вебхука в логах и Sentry (docs/09 §4).
WEBHOOK_PATH_REDACTED = BOT_WEBHOOK_PATH + "/***"

# Повторы отправки уведомлений при сетевых сбоях (docs/05 §6.4): паузы 1, 5, 15 минут,
# после третьего повтора уведомление получает статус failed.
NOTIFICATION_RETRY_DELAYS_SECONDS = (60, 300, 900)

# Доставка уведомлений (docs/05 §6.4)
NOTIFICATION_BATCH_SIZE = 25
NOTIFICATION_MAX_BATCHES = 100
# ~25 сообщений в секунду: лимит Telegram на массовые отправки
NOTIFICATION_SEND_PAUSE_SECONDS = 0.04
QUIET_HOURS_START = 22
QUIET_HOURS_END = 8
# Урок ближе этого срока делает отмену или перенос срочными (игнорируют тихие часы)
URGENT_LESSON_CHANGE_HOURS = 12

# Воркер (docs/03 §9, docs/10 §8)
HEARTBEAT_CRON = "*/5 * * * *"
HEARTBEAT_TIMEOUT_SECONDS = 10

# Напоминания и обслуживание (docs/03 §9, docs/05 §6)
LESSON_REMINDER_MINUTES = 30
# Задача идёт раз в минуту: напоминание ставится заранее (с запасом в одну минуту) на точный момент
LESSON_REMINDER_LOOKAHEAD_MINUTES = 31
# Если воркер простоял, позднее напоминание ещё полезно, но не позже этого опоздания
LESSON_REMINDER_LATE_TOLERANCE_MINUTES = 5
HOMEWORK_REMINDER_HOURS = 24
HOMEWORK_REMINDER_LOOKAHEAD_MINUTES = 5
UNMARKED_LESSON_AFTER_MINUTES = 60
# Урок без отметки старше этого срока уже не напоминаем (иначе первый запуск завалит сообщениями)
UNMARKED_LESSON_LOOKBACK_DAYS = 14
TOKEN_RETENTION_DAYS = 1
# Расписание задач (cron, UTC)
CRON_EVERY_MINUTE = "* * * * *"
CRON_EVERY_5_MINUTES = "*/5 * * * *"
CRON_EVERY_15_MINUTES = "*/15 * * * *"
CRON_LESSON_GENERATION = "0 3 * * *"
CRON_LINKS_CLEANUP = "30 3 * * *"
