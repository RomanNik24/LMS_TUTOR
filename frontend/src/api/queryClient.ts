/** Настройки TanStack Query (docs/12 §4.4). */
import { QueryClient } from "@tanstack/react-query";

import { isUnauthenticated } from "./errors";

const MAX_RETRIES = 2;

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // 401 не повторяем: пользователь просто не вошёл
        retry: (failureCount, error) => !isUnauthenticated(error) && failureCount < MAX_RETRIES,
        refetchOnWindowFocus: false,
      },
    },
  });
}
