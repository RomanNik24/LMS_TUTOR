/**
 * ВСЕ тексты интерфейса живут здесь (docs/12 §10.2, docs/06 B3).
 * Язык — русский, идентификаторы — английские.
 * Пока минимальный набор ключей для каркаса; расширяется по мере появления экранов.
 */
export const texts = {
  app: {
    title: "Ромчик",
    greeting: "Привет, Ромчик",
  },
  login: {
    title: "Ромчик | ИнфоМат",
    openViaBot: "Войди через Telegram-бота",
    openBot: "Открыть бота",
    signingIn: "Входим…",
    retry: "Повторить",
    linkHint: "Нажми «Войти», чтобы открыть приложение. Ссылка сработает только один раз.",
    linkButton: "Войти",
  },
  hello: {
    greeting: "Привет, {name}",
    roleLabel: "Роль",
  },
  roles: {
    student: "Ученик",
    manager: "Менеджер",
    owner: "Владелец",
  },
  common: {
    loading: "Загрузка…",
    back: "Назад",
    cancel: "Отмена",
    save: "Сохранить",
    close: "Закрыть",
    logout: "Выход",
    logoutFailed: "Не получилось выйти. Попробуй ещё раз",
    mainNavigation: "Основная навигация",
    brand: "Ромчик | ИнфоМат",
    brandFirst: "Ромчик",
    brandSecond: "ИнфоМат",
    profileAvatar: "Профиль",
    notFound: "Эта страница недоступна",
    toHome: "На главную",
  },
  nav: {
    student: {
      schedule: "Расписание",
      homework: "ДЗ",
      reports: "Отчёты",
    },
    admin: {
      today: "Сегодня",
      schedule: "Расписание",
      homework: "ДЗ",
      students: "Ученики",
      more: "Ещё",
      exams: "Пробники",
      catalog: "Каталог",
      finance: "Финансы",
      staff: "Сотрудники",
    },
  },
  /** Пустые состояния (docs/07 §6.16, §8.2) */
  empty: {
    studentSchedule: {
      title: "Расписание",
      text: "Пока уроков нет. Роман добавит расписание, и оно появится здесь",
    },
    studentHomework: {
      title: "ДЗ",
      text: "Все ДЗ сделаны. Новые появятся здесь",
    },
    studentReports: {
      title: "Отчёты",
      text: "Пока мало данных. Графики появятся после первых проверенных ДЗ",
    },
    adminStudents: {
      title: "Ученики",
      text: "Учеников пока нет. Создайте первый профиль",
    },
    adminReviewQueue: {
      title: "ДЗ",
      text: "Очередь пуста. Всё проверено",
    },
    soon: "Раздел скоро появится",
  },
  /** Статус-бейджи — единственная таблица текстов (docs/07 §6.6) */
  status: {
    "lesson.scheduled": "Запланирован",
    "lesson.completed": "Проведён",
    "lesson.cancelled": "Отменён",
    "homework.assigned": "Выдано",
    "homework.submitted": "На проверке",
    "homework.needs_revision": "На доработку",
    "homework.graded": "Проверено",
    "homework.expired": "Сгорело",
    "homework.overdue": "Просрочено",
    "attendance.pending": "Не отмечено",
    "attendance.attended": "Был",
    "attendance.no_show": "Не пришёл",
    "attendance.cancelled": "Отменено",
    "bot.blocked": "Бот заблокирован",
  },
  /** Сообщения интерфейса (docs/07 §8.2) */
  messages: {
    saved: "Сохранено",
    networkError: "Нет соединения. Проверь интернет и повтори",
    offlineBanner: "Нет соединения. Проверим ещё раз",
    serverError: "Что-то пошло не так. Попробуй ещё раз",
    noAccess: "Эта страница недоступна",
    archiveConfirm: "Архивировать ученика? Данные и статистика сохранятся",
    invitationCreated: "Ссылка создана. Действует 7 дней, откроется один раз",
  },
  errors: {
    unknown: "Что-то пошло не так. Попробуй позже.",
    network: "Нет связи с сервером. Проверь интернет и попробуй ещё раз.",
    unauthenticated: "Не удалось войти. Открой приложение через бота или войди по ссылке из бота.",
    permission_denied: "Недостаточно прав для этого действия.",
    not_found: "Не найдено.",
    validation_error: "Проверь введённые данные.",
    rate_limited: "Слишком много запросов. Подожди минуту и попробуй снова.",
    login_link_invalid: "Ссылка недействительна или устарела. Попроси новую у Романа.",
    invite_already_used: "Ссылка уже использована. Попроси новую у Романа.",
    internal_error: "Произошла внутренняя ошибка. Попробуй позже.",
  },
} as const;

/** Ключи кодов ошибок, для которых есть понятный текст (см. docs/08 §1). */
export type ErrorTextKey = keyof typeof texts.errors;

/**
 * Формы множественного числа (docs/12 §10.2): plural(2, ["урок", "урока", "уроков"]) → "урока".
 * Русские правила: 1 → f1; 2–4 (кроме 12–14) → f2; иначе f3.
 */
export function plural(count: number, forms: readonly [string, string, string]): string {
  const n = Math.abs(count) % 100;
  const one = n % 10;
  if (n >= 11 && n <= 14) return forms[2];
  if (one === 1) return forms[0];
  if (one >= 2 && one <= 4) return forms[1];
  return forms[2];
}
