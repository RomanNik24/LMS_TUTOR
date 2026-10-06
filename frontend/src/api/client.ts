/**
 * Типизированный HTTP-клиент (docs/12 §4.2). Cookie сессии отправляются автоматически
 * (тот же домен), заголовок X-Requested-With — защита от CSRF (docs/09 §2.3.1).
 * Origin браузер добавляет сам.
 */
import createClient from "openapi-fetch";

import type { paths } from "./schema";

export const CSRF_HEADERS = { "X-Requested-With": "XMLHttpRequest" } as const;

/**
 * Пути в схеме уже содержат префикс /api/v1. baseUrl — origin текущей страницы:
 * это тот же адрес, что и относительный запрос, но работает и там, где fetch
 * требует абсолютный URL (тесты в jsdom).
 */
export function createApiClient(baseUrl: string = window.location.origin) {
  return createClient<paths>({
    baseUrl,
    credentials: "same-origin",
    // fetch берём в момент запроса, а не при создании клиента: так его можно
    // подменить позже (MSW в тестах подключается после импорта модулей).
    fetch: (request) => globalThis.fetch(request),
    headers: { ...CSRF_HEADERS },
  });
}

export const api = createApiClient();
