/**
 * Sentry фронтенда (docs/09 §6, T8.06). Включается только при заданном `VITE_SENTRY_DSN`; без него
 * SDK не загружается вообще (динамический импорт). Персональных данных в событиях нет: отправка PII
 * выключена, `user`, cookie, заголовки, тела запросов и адресная строка очищаются в `scrubEvent`,
 * а из URL удаляются запрос, фрагмент и токены (`/login/<токен>`, `tgWebAppData`, `initData`).
 */

const TOKEN_SEGMENT = /^[A-Za-z0-9_-]{20,}$/;
const PLACEHOLDER = "[token]";
const SENSITIVE_FIELDS = ["user", "request", "contexts", "extra"] as const;

/** Адрес без запроса и фрагмента; длинные «токеноподобные» сегменты пути заменены. */
export function scrubUrl(value: string): string {
  const [withoutFragment] = value.split("#");
  const [withoutQuery] = (withoutFragment ?? "").split("?");
  return (withoutQuery ?? "")
    .split("/")
    .map((segment) => (TOKEN_SEGMENT.test(segment) ? PLACEHOLDER : segment))
    .join("/");
}

type Scrubbable = {
  user?: unknown;
  request?: { url?: string };
  breadcrumbs?: { data?: Record<string, unknown>; message?: string }[];
  transaction?: string;
  extra?: unknown;
  contexts?: unknown;
};

/** Убирает из события всё, что может содержать персональные данные или токены. */
export function scrubEvent<T extends Scrubbable>(event: T): T {
  const clean: Scrubbable = { ...event };
  for (const field of SENSITIVE_FIELDS) {
    if (field === "request") continue;
    delete clean[field];
  }
  if (event.request?.url !== undefined) clean.request = { url: scrubUrl(event.request.url) };
  else delete clean.request;
  if (event.transaction !== undefined) clean.transaction = scrubUrl(event.transaction);
  if (event.breadcrumbs !== undefined) {
    clean.breadcrumbs = event.breadcrumbs.map(({ data, message }) => {
      const url = data?.["url"];
      return {
        ...(message === undefined ? {} : { message: scrubUrl(message) }),
        ...(typeof url === "string" ? { data: { url: scrubUrl(url) } } : {}),
      };
    });
  }
  return clean as T;
}

/** Запускает Sentry, если DSN задан. Ошибка инициализации не должна ломать приложение. */
export async function initSentry(dsn: string | undefined): Promise<boolean> {
  if (dsn === undefined || dsn.trim() === "") return false;
  try {
    const Sentry = await import("@sentry/react");
    Sentry.init({
      dsn,
      sendDefaultPii: false,
      tracesSampleRate: 0,
      beforeSend: (event) => scrubEvent(event),
    });
    return true;
  } catch {
    return false;
  }
}
