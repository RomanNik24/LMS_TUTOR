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
  /** Админка: ученики, сотрудники, приглашения (docs/07 §9.2.2–9.2.4, §9.2.13) */
  admin: {
    students: {
      newStudent: "Новый ученик",
      search: "Поиск по имени",
      filterActive: "Активные",
      filterArchived: "Архив",
      classLabel: (value: number) => `${String(value)} класс`,
      invitePending: "Приглашение не принято",
      listLoadError: "Не получилось загрузить учеников",
      noResults: "Никого не нашли. Измени поиск",
      noArchived: "В архиве никого нет",
      loadMore: "Показать ещё",
      archivedBadge: "В архиве",
      tabs: { overview: "Обзор", finance: "Финансы" },
      overview: {
        profile: "Профиль",
        timezone: "Часовой пояс",
        subjects: "Предметы",
        video: "Телемост",
        board: "Доска",
        notes: "Заметки преподавателя",
        notesPrivate: "Видны только персоналу",
        none: "Не указано",
        telegram: "Telegram",
        telegramLinked: "Подключён",
        telegramNotLinked: "Не подключён",
      },
      finance: { lessonPrice: "Цена занятия", perLesson: (value: string) => `${value} ₽ за урок` },
      actions: {
        edit: "Редактировать",
        invite: "Приглашение",
        archive: "Архивировать",
        restore: "Вернуть из архива",
        unlink: "Отвязать Telegram",
        back: "К списку",
      },
      archiveTitle: (name: string) => `Архивировать ${name}?`,
      archiveText: "Данные и статистика сохранятся, вход будет закрыт",
      archiveConfirm: "Архивировать",
      unlinkTitle: (name: string) => `Отвязать Telegram у ${name}?`,
      unlinkText: "Ученик не сможет войти, пока не получит новое приглашение",
      unlinkConfirm: "Отвязать",
      notFound: "Ученик не найден",
      form: {
        createTitle: "Новый ученик",
        editTitle: "Редактирование",
        name: "Имя",
        schoolClass: "Класс",
        subjects: "Предметы",
        timezone: "Часовой пояс",
        video: "Ссылка на Телемост",
        board: "Ссылка на доску",
        price: "Цена занятия, ₽",
        notes: "Заметки преподавателя",
        submitCreate: "Создать ученика",
        submitEdit: "Сохранить",
        errors: {
          nameRequired: "Введи имя",
          nameTooLong: "Не длиннее 150 символов",
          classRange: "Класс — число от 1 до 11",
          urlHttps: "Ссылка должна начинаться с https://",
          urlTooLong: "Не длиннее 500 символов",
          priceRange: "Цена — целое число от 0 до 1 000 000",
          notesTooLong: "Не длиннее 5000 символов",
          timezoneRequired: "Выбери часовой пояс",
        },
      },
    },
    subjects: { informatics: "Информатика", math: "Математика" },
    timezones: {
      "Europe/Moscow": "Москва (UTC+3)",
      "Europe/Samara": "Самара (UTC+4)",
      "Asia/Yekaterinburg": "Екатеринбург (UTC+5)",
      "Asia/Omsk": "Омск (UTC+6)",
      "Asia/Novosibirsk": "Новосибирск (UTC+7)",
      "Asia/Krasnoyarsk": "Красноярск (UTC+7)",
      "Asia/Irkutsk": "Иркутск (UTC+8)",
      "Asia/Yakutsk": "Якутск (UTC+9)",
      "Asia/Vladivostok": "Владивосток (UTC+10)",
      "Europe/Kaliningrad": "Калининград (UTC+2)",
    },
    invitation: {
      title: "Приглашение",
      preparing: "Готовим ссылку…",
      hint: "Откроется один раз. Действует 7 дней",
      copy: "Скопировать",
      copied: "Ссылка скопирована",
      copyFailed: "Не получилось скопировать. Выдели ссылку и скопируй вручную",
      share: "Поделиться",
      shareText: "Твоя ссылка для входа в «Ромчик | ИнфоМат»",
      reissue: "Перевыпустить",
      revoke: "Отозвать",
      revoked: "Приглашение отозвано",
      expires: (date: string) => `Действует до ${date}`,
      error: "Не получилось создать приглашение",
    },
    staff: {
      newStaff: "Новый сотрудник",
      listLoadError: "Не получилось загрузить сотрудников",
      empty: { title: "Сотрудников пока нет", text: "Добавь первого сотрудника" },
      roles: { owner: "Владелец", manager: "Менеджер" },
      showArchived: "Показывать архивных",
      archivedBadge: "В архиве",
      invitePending: "Приглашение не принято",
      actions: { invite: "Приглашение", archive: "Архивировать", edit: "Изменить" },
      archiveTitle: (name: string) => `Архивировать ${name}?`,
      archiveText: "Вход будет закрыт, данные сохранятся",
      archiveConfirm: "Архивировать",
      form: {
        createTitle: "Новый сотрудник",
        editTitle: "Изменить сотрудника",
        name: "Имя",
        role: "Роль",
        timezone: "Часовой пояс",
        submitCreate: "Создать",
        submitEdit: "Сохранить",
        nameRequired: "Введи имя",
        nameTooLong: "Не длиннее 150 символов",
      },
    },
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
    last_owner: "Нельзя понизить или архивировать последнего владельца.",
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
