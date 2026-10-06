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
    retry: "Попробовать ещё раз",
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
