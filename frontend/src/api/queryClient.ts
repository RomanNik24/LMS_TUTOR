/** Настройки TanStack Query (docs/12 §4.4). */
import { QueryClient } from "@tanstack/react-query";

import { isUnauthenticated } from "./errors";

const MAX_RETRIES = 2;

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      // Без «паузы офлайн»: при обрыве связи запрос сразу падает с ошибкой и экран показывает
      // «Повторить», а не вечный скелетон (T8.05).
      mutations: { networkMode: "always" },
      queries: {
        networkMode: "always",
        // 401 не повторяем: пользователь просто не вошёл
        retry: (failureCount, error) => !isUnauthenticated(error) && failureCount < MAX_RETRIES,
        refetchOnWindowFocus: false,
      },
    },
  });
}
