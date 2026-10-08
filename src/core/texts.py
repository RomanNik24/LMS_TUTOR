"""Тексты ошибок и сообщений бэкенда (docs/06 A7, ADR 0001).

Все пользовательские тексты бэкенда живут здесь. Тон: ученику «ты»,
персоналу нейтрально. Тексты не содержат токенов и персональных данных.
"""

from datetime import date, datetime

# --- Приглашения и вход (docs/05 §3.1) ---
INVITE_INVALID = "Ссылка недействительна или устарела. Попроси у преподавателя новую."
INVITE_ALREADY_USED = "Ссылка уже использована. Попроси у преподавателя новую."
INVITE_NOT_FOUND = "Активного приглашения нет."
TELEGRAM_ALREADY_LINKED = (
    "Этот Telegram-аккаунт уже привязан к другому профилю. Сообщи преподавателю."
)
TOO_MANY_ATTEMPTS = "Слишком много неудачных попыток. Попробуй позже."
USER_NOT_FOUND = "Пользователь не найден."
USER_ARCHIVED = "Пользователь в архиве."
TELEGRAM_NOT_LINKED = "Telegram не привязан."
LOGIN_LINK_INVALID = (
    "Ссылка входа недействительна или устарела. Запроси новую в боте командой /web."
)
OWNER_TELEGRAM_ID_TAKEN = "Этот Telegram ID уже принадлежит пользователю не с ролью владельца."
UNAUTHENTICATED_TELEGRAM = (
    "Не удалось войти. Открой приложение через бота или запроси ссылку входа командой /web."
)

OWNER_CANNOT_UNLINK = (
    "Владелец не может отвязать свой Telegram: войти снова будет нельзя. "
    "Для смены аккаунта обратитесь к администратору сервера."
)
OWNER_DISPLAY_NAME = "Владелец"

# --- Ученики (docs/08 §5.2, T2.02) ---
STUDENT_NOT_FOUND = "Ученик не найден."
STUDENT_PRICE_OWNER_ONLY = "Цену занятия видит и меняет только владелец."
STUDENT_UNKNOWN_SUBJECT = "Неизвестный предмет."
STUDENT_INVALID_TEACHER = "Ведущим преподавателем может быть только активный владелец или менеджер."
STUDENT_ALREADY_ARCHIVED = "Ученик уже в архиве."
STUDENT_NOT_ARCHIVED = "Ученик не в архиве."
STUDENT_URL_NOT_HTTPS = "Ссылка должна начинаться с https://."
STUDENT_UPDATE_EMPTY = "Укажите хотя бы одно поле для изменения."
STUDENT_FIELD_NOT_NULLABLE = "Это поле нельзя очистить."
LIST_PARAMS_INVALID = "Неверные параметры списка: limit от 1 до 200, offset не меньше 0."

# --- Каталог услуг (docs/08 §5.7, T8.01) ---
CATALOG_ITEM_NOT_FOUND = "Карточка каталога не найдена."
CATALOG_FIELD_BLANK = "Поле не может быть пустым."
CATALOG_REORDER_INVALID = "Список порядка должен содержать все карточки каталога по одному разу."

BOT_USERNAME_UNKNOWN = "Не удалось определить имя бота. Задайте BOT_USERNAME в настройках."

# --- Сотрудники (docs/08 §5.3, T2.03) ---
STAFF_NOT_FOUND = "Сотрудник не найден."
STAFF_LAST_OWNER = "Нельзя понизить или архивировать последнего владельца."
STAFF_ALREADY_ARCHIVED = "Сотрудник уже в архиве."

# --- Расписание и уроки (docs/08 §5.4, T3.04) ---
LESSON_OVERLAP = "У преподавателя уже есть урок в это время. Выберите другое время."
LESSON_END_BEFORE_START = "Урок должен заканчиваться позже, чем начинается."
LESSON_TOO_LONG = "Урок не может быть длиннее 12 часов."
LESSON_STUDENT_NOT_FOUND = "Ученик не найден."
LESSON_STUDENT_ARCHIVED = "Ученик в архиве: добавить его на урок нельзя."
LESSON_STUDENTS_DUPLICATE = "Один ученик указан дважды."
LESSON_UNKNOWN_SUBJECT = "Неизвестный предмет."
LESSON_INVALID_TEACHER = "Урок может вести только активный владелец или менеджер."

LESSON_NOT_FOUND = "Урок не найден."
LESSON_NOT_SCHEDULED = "Урок уже проведён или отменён: его нельзя изменить."
LESSON_ALREADY_COMPLETED = "Урок уже отмечен как проведённый."
LESSON_MARKS_MISMATCH = "Отметьте всех участников урока: ни больше, ни меньше."
LESSON_NOT_PARTICIPANT = "Этот ученик не участвует в уроке."
LESSON_MARK_PENDING = "Посещаемость должна быть «был», «не пришёл» или «отменено»."
LESSON_CANCEL_REASON_TOO_LONG = "Причина отмены не длиннее 255 символов."

LESSON_PERIOD_INVALID = "Период указан неверно: конец позже начала и не больше года."
LESSON_UPDATE_EMPTY = "Укажите хотя бы одно поле для изменения."
LESSON_FIELD_NOT_NULLABLE = "Это поле нельзя очистить."
TEMPLATE_TIME_HAS_TZ = "Время начала задаётся без часового пояса: пояс указывается отдельно."
TEMPLATE_NOT_FOUND = "Шаблон расписания не найден."
TEMPLATE_ENDS_BEFORE_START = "Дата окончания не может быть раньше даты начала."
TEMPLATE_UPDATE_EMPTY = "Укажите хотя бы одно поле для изменения."
TEMPLATE_FIELD_NOT_NULLABLE = "Это поле нельзя очистить."
TEMPLATE_NO_PARTICIPANTS = "У шаблона должен остаться хотя бы один участник."
TEMPLATE_HORIZON_INVALID = "Горизонт генерации — от 1 до 52 недель."

# --- Файлы ДЗ (docs/09, T4.05) ---
FILE_UNSUPPORTED = "Этот тип файла не поддерживается. Загрузите JPEG, PNG, HEIC или PDF."
FILE_TOO_LARGE = "Файл слишком большой: не больше 10 МБ."
FILE_EMPTY = "Файл пустой."
FILES_LIMIT = "Можно загрузить не больше 10 файлов."
FILE_NOT_FOUND = "Файл не найден."
ASSIGNMENT_NOT_FOUND = "Выдача не найдена."
HOMEWORK_NOT_FOUND = "Задание не найдено."
ASSIGNMENT_NOT_EDITABLE = "Файлы нельзя менять: работа уже проверена или срок вышел."
FILE_DEFAULT_NAME = "файл"

# --- Домашние задания (docs/04 §5, T4.06) ---
HOMEWORK_TITLE_REQUIRED = "Укажите название задания."
HOMEWORK_EXAM_TYPE_REQUIRED = "Для пробника укажите тип экзамена."
HOMEWORK_SUBJECT_REQUIRED = "Укажите предмет задания."
HOMEWORK_MAX_SCORE_REQUIRED = "Укажите число заданий (максимальный балл)."
HOMEWORK_DUE_AT_REQUIRED = "Для фиксированного срока укажите дату и время."
HOMEWORK_DUE_IN_PAST = "Срок сдачи должен быть в будущем."
HOMEWORK_NO_NEXT_LESSON = "У ученика нет запланированного урока: выберите срок вручную."
HOMEWORK_EXAM_TYPE_UNKNOWN = "Тип экзамена не найден."
HOMEWORK_LESSON_UNKNOWN = "Урок не найден."
HOMEWORK_SUBJECT_MISMATCH = "Предмет не совпадает с предметом экзамена."
HOMEWORK_STUDENTS_REQUIRED = "Выберите хотя бы одного ученика."

ASSIGNMENT_EXPIRED = "Срок сдачи вышел, работу сдать нельзя. Обратитесь к преподавателю."
ASSIGNMENT_NOT_SUBMITTABLE = "Работа уже сдана или проверена."
SUBMISSION_NO_FILES = "Загрузите хотя бы один файл или нажмите «Сделал»."
STUDENT_COMMENT_TOO_LONG = "Комментарий не длиннее 2000 символов."

SCORE_OUT_OF_RANGE = "Балл должен быть целым числом от 0 до {max_score}."

# --- Пробные экзамены (docs/04 §6, docs/08 §5.6) ---
MOCK_EXAM_UPDATE_EMPTY = "Укажите хотя бы одно поле для изменения."
MOCK_EXAM_NOT_FOUND = "Результат пробника не найден."
MOCK_EXAM_EXAM_TYPE_UNKNOWN = "Тип экзамена не найден."
MOCK_EXAM_LINKED_TO_HOMEWORK = (
    "Результат создан из ДЗ: исправьте оценку выдачи, и он обновится сам."
)
MOCK_EXAM_GEOMETRY_NOT_APPLICABLE = "Баллы по геометрии указываются только для ОГЭ математики."
MOCK_EXAM_GEOMETRY_TOO_BIG = "Баллы по геометрии не могут превышать первичный балл."
MOCK_EXAM_SCORE_ABOVE_MAX = "Первичный балл не может быть больше максимума варианта."
ASSIGNMENT_NOT_GRADABLE = "Эту работу пока нельзя оценить: ученик ещё не сдал её."
ASSIGNMENT_NOT_RETURNABLE = "Вернуть на доработку можно только сданную работу."
RETURN_COMMENT_REQUIRED = "Напишите, что нужно доработать."
RETURN_DUE_NOT_FOUND = "У ученика нет запланированного урока: выберите новый срок вручную."

EXTENSION_LIMIT = "Срок уже переносили два раза: больше переносить нельзя."
ASSIGNMENT_NOT_EXTENDABLE = (
    "Срок можно переносить только у работы, которая ещё не сдана и не истекла."
)
EXTENSION_DUE_NOT_LATER = "Новый срок должен быть позже текущего."

# --- Общие ошибки API (docs/08 §1) ---
API_UNAUTHENTICATED = "Требуется вход."
API_RATE_LIMITED = "Слишком много запросов. Попробуйте позже."
API_CSRF_REJECTED = "Запрос отклонён."
API_INTERNAL_ERROR = "Произошла внутренняя ошибка. Попробуйте позже."
API_EXTERNAL_SERVICE_UNAVAILABLE = "Внешний сервис временно недоступен. Попробуйте позже."
AUTH_INIT_DATA_INVALID = "Не удалось подтвердить вход через Telegram."
API_NOT_FOUND = "Ресурс не найден."
API_VALIDATION_FAILED = "Ошибка валидации данных."
API_NOT_FOUND_DEFAULT = "Не найдено."
API_PERMISSION_DENIED = "Недостаточно прав для этого действия."
API_CONFLICT_DEFAULT = "Конфликт с текущим состоянием данных."
API_BUSINESS_RULE_DEFAULT = "Действие нарушает правило сервиса."
ME_TIMEZONE_UNKNOWN = "Неизвестный часовой пояс (нужен IANA, например Europe/Moscow)"
ME_NAME_BLANK = "Имя не может быть пустым"
ME_UPDATE_EMPTY = "Укажите timezone или display_name"

# --- Бот: приветствия и меню (docs/05 §2–§3, docs/07 §8.3; ученику «ты», персоналу нейтрально) ---
BOT_GUEST_GREETING = (
    "Привет! Это бот репетитора Романа: информатика и математика, ОГЭ и ЕГЭ. "
    "Загляни в каталог услуг или напиши Роману напрямую."
)
BOT_STUDENT_GREETING = "Привет, {name}! Расписание и ДЗ — в приложении."
BOT_STAFF_GREETING = "Добро пожаловать, {name}. Расписание, ученики и ДЗ — в Admin App."
BOT_ACCESS_CLOSED = "Доступ закрыт. Обратись к преподавателю."
BOT_ALREADY_LOGGED_IN = "Ты уже в системе."
BOT_APP_UNAVAILABLE = "Приложение пока недоступно."
BOT_OPEN_APP_STUDENT = "Открыть приложение"
BOT_OPEN_APP_STAFF = "Открыть Admin App"
BOT_BUTTON_SCHEDULE = "Расписание"
BOT_BUTTON_TODAY = "Сегодня"
BOT_BUTTON_HOMEWORK = "Мои ДЗ"
BOT_BUTTON_REVIEW = "На проверку"
BOT_BUTTON_CATALOG = "Каталог услуг"
BOT_BUTTON_CONTACT = "Связаться с преподавателем"
BOT_CATALOG_EMPTY = "Каталог скоро появится. Напиши преподавателю."
BOT_CONTACT = "Напиши преподавателю напрямую."
BOT_CONTACT_UNAVAILABLE = "Контакт преподавателя пока не настроен."
BOT_CONTACT_LINK = "Написать преподавателю"

# --- Бот: приглашение, перепривязка, выход, вход в браузере ---
BOT_RELINK_CONFIRM = (
    "К этому профилю уже привязан другой Telegram-аккаунт. Привязать этот аккаунт вместо него?"
)
BOT_RELINK_YES = "Да, привязать этот аккаунт"
BOT_RELINK_CANCEL = "Отмена"
BOT_RELINK_CANCELLED = "Отменено. Прежняя привязка осталась."
BOT_RELINK_STATE_LOST = "Подтверждение устарело. Открой ссылку из приглашения ещё раз."
BOT_LOGOUT_CONFIRM = "Выйти? Чтобы войти снова, понадобится новая ссылка от преподавателя."
BOT_LOGOUT_YES = "Да, выйти"
BOT_LOGOUT_DONE = "Выход выполнен. Чтобы войти снова, нужна новая ссылка от преподавателя."
BOT_LOGOUT_CANCELLED = "Отменено."
BOT_WEB_LINK = "Ссылка для входа в браузере. Действует 10 минут и срабатывает один раз:\n{url}"
BOT_WEB_GUEST = (
    "Вход в браузере доступен после подключения. Попроси у преподавателя ссылку-приглашение."
)
BOT_FALLBACK_HINT = "Воспользуйся меню или командой /help."
BOT_ERROR_GENERIC = "Что-то пошло не так. Повторите попытку позже."

# --- Бот: справка (/help) ---
BOT_HELP_GUEST = (
    "Это бот репетитора Романа.\n\n"
    "Каталог услуг — посмотреть, чем занимаемся.\n"
    "Связаться с преподавателем — написать напрямую.\n\n"
    "Если у тебя есть ссылка-приглашение, просто открой её."
)
BOT_HELP_STUDENT = (
    "/app — открыть приложение\n"
    "/today — уроки на ближайшие 24 часа\n"
    "/hw — активные ДЗ\n"
    "/web — ссылка для входа в браузере\n"
    "/logout — выйти из аккаунта\n"
    "/help — эта справка"
)
BOT_HELP_STAFF = (
    "/app — открыть Admin App\n"
    "/today — уроки на сегодня\n"
    "/hw — очередь проверки\n"
    "/web — ссылка для входа в браузере\n"
    "/logout — отвязать аккаунт\n"
    "/help — справка"
)

# --- Бот: описания команд (setMyCommands) ---
BOT_CMD_START = "Начало работы"
BOT_CMD_APP = "Открыть приложение"
BOT_CMD_TODAY = "Расписание на сегодня"
BOT_CMD_HW_STUDENT = "Мои ДЗ"
BOT_CMD_HW_STAFF = "На проверку"
BOT_CMD_WEB = "Вход в браузере"
BOT_CMD_LOGOUT = "Выйти из аккаунта"
BOT_CMD_HELP = "Справка"


# --- Бот: расписание (/today, T3.08) ---
BOT_STUDENT_NO_LESSONS = "В ближайшие 24 часа уроков нет. Всё расписание — в приложении."
BOT_STAFF_NO_LESSONS = "На сегодня уроков нет."

# --- Бот: ДЗ (/hw, docs/05 §3.6) ---
BOT_HW_STUDENT_EMPTY = "Активных ДЗ нет. Новые появятся в приложении и здесь."
BOT_HW_DUE = "Сдать до {when}"
BOT_HW_OVERDUE = "Срок вышел. Напиши Роману"
BOT_HW_MORE = "И ещё {count} — в приложении."
BOT_HW_OPEN = "Открыть в приложении"
BOT_HW_QUEUE_EMPTY = "Очередь проверки пуста."
BOT_HW_QUEUE_HEADER = "На проверку: {count}"
BOT_HW_QUEUE_MORE = "…и ещё {count}"
BOT_STAFF_TODAY_HEADER = "Сегодня, {date}:"
BOT_LINK_VIDEO = "Телемост"
BOT_LINK_BOARD = "Доска"
BOT_LESSON_DONE_MARK = "проведён"
BOT_LESSON_CANCELLED_MARK = "отменён"
SUBJECT_NAMES = {"informatics": "Информатика", "math": "Математика"}
MONTHS_GENITIVE = (
    "янв",
    "фев",
    "мар",
    "апр",
    "мая",
    "июн",
    "июл",
    "авг",
    "сен",
    "окт",
    "ноя",
    "дек",
)
WEEKDAYS_SHORT = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")


def subject_name(code: str) -> str:
    """Название предмета по коду (неизвестный код показывается как есть)."""
    return SUBJECT_NAMES.get(code, code)


def short_date(day: date) -> str:
    """Дата для сообщений бота: «вт, 14 окт»."""
    return f"{WEEKDAYS_SHORT[day.weekday()]}, {day.day} {MONTHS_GENITIVE[day.month - 1]}"


def lesson_when(start: datetime, end: datetime) -> str:
    """Время урока в поясе получателя: «вт, 14 окт, 17:00–18:00» (аргументы уже локальные)."""
    return f"{short_date(start.date())}, {start:%H:%M}–{end:%H:%M}"


# --- Уведомления (docs/05 §6): ученику на «ты», персоналу нейтрально, без родовых окончаний ---
NOTIFY_LESSON_REMINDER = "⏰ Через 30 минут урок: {subject}, {time}."
NOTIFY_HOMEWORK_DEADLINE = "📌 Завтра дедлайн ДЗ «{title}». Не забудь сдать."
NOTIFY_HOMEWORK_GRADED = "✅ ДЗ «{title}» проверено: {score} из {max_score}."
NOTIFY_HOMEWORK_RETURNED = "↩ ДЗ «{title}» вернулось на доработку. Комментарий: {comment}"
NOTIFY_HOMEWORK_ASSIGNED = "📝 Новое ДЗ: «{title}». Срок: {due}."
NOTIFY_LESSON_CANCELLED = "❌ Урок {when} отменён."
NOTIFY_LESSON_RESCHEDULED = "🔁 Урок перенесён: было {old}, стало {new}."
NOTIFY_HOMEWORK_SUBMITTED = "📥 Сдано ДЗ «{title}»: {student}."
NOTIFY_HOMEWORK_EXPIRED = "⌛ ДЗ «{title}» сгорело: {student}."
NOTIFY_LESSON_UNMARKED = "📋 Нет отметки об уроке: {subject}, {when}."
NOTIFY_STUDENT_JOINED = "👋 Ученик принял приглашение: {student}."
NOTIFY_BUTTON_OPEN_HOMEWORK = "Открыть ДЗ"
NOTIFY_BUTTON_OPEN_APP = "Открыть приложение"
NOTIFY_BUTTON_OPEN_ADMIN = "Открыть Admin App"


def local_when(moment: datetime) -> str:
    """Момент в поясе получателя: «вт, 14 окт, 17:00» (аргумент уже локальный)."""
    return f"{short_date(moment.date())}, {moment:%H:%M}"


# --- Утренняя сводка персоналу (docs/05 §6.3) ---
DIGEST_TITLE = "☀ Сводка на {date}"
DIGEST_LESSONS = "Уроки сегодня ({count}):"
DIGEST_LESSON_LINE = "• {time} {subject}: {students}"
DIGEST_REVIEW = "ДЗ на проверку: {count}"
DIGEST_REVIEW_LINE = "• {student} — {title}"
DIGEST_UNSUBMITTED = "Не сдано к сегодняшним урокам ({count}):"
DIGEST_UNSUBMITTED_LINE = "• {student} — {title}, срок {due}"
DIGEST_UNMARKED = "Уроки без отметки ({count}):"
DIGEST_UNMARKED_LINE = "• {when}, {subject}"
DIGEST_DEADLINES = "Дедлайны ближайших 24 часов ({count}):"
DIGEST_DEADLINE_LINE = "• {student} — {title}, {due}"
DIGEST_MORE = "…и ещё {count}"
DIGEST_EARNED = "Заработано в этом месяце: {amount} ₽"

# Выгрузка CSV заработка (T7.02): заголовки колонок; только нужные поля
FINANCE_CSV_HEADER = ("Дата", "Ученик", "Предмет", "Сумма, ₽")


def money(amount: int) -> str:
    """Сумма в рублях с пробелом между тысячами: ``12 500``."""
    return f"{amount:,}".replace(",", "\u00a0")
