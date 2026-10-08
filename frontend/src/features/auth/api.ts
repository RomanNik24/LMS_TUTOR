/**
 * Запросы аутентификации (docs/12 §5.3). Запросы к API живут только в api.ts возможностей (features).
 * Данные о пользователе хранит TanStack Query под ключом ["me"].
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/api/client";
import { unwrap, unwrapEmpty } from "@/api/errors";
import type { components } from "@/api/schema";
import { getInitData, isTelegramMiniApp } from "@/lib/telegram";

export type Me = components["schemas"]["MeResponse"];
export type Role = Me["role"];

export const ME_QUERY_KEY = ["me"] as const;

const ME_STALE_TIME_MS = 5 * 60_000;

/** Вход по initData текущего запуска Mini App уже выполнен в этой вкладке. */
let launchLoginDone = false;

/**
 * Кто сейчас пользователь. В Mini App первым делом входим по initData запуска: cookie сессии может
 * остаться от другого аккаунта (например, тот же Telegram-клиент раньше открывал приложение
 * учеником), и без этого владелец видел бы чужой экран. Дальше — обычный GET /me.
 */
async function fetchMe(): Promise<Me> {
  const initData = isTelegramMiniApp() ? getInitData() : null;
  if (initData !== null && !launchLoginDone) {
    const me = unwrap(await api.POST("/api/v1/auth/telegram", { body: { init_data: initData } }));
    launchLoginDone = true;
    return me;
  }
  return unwrap(await api.GET("/api/v1/me"));
}

/** Для тестов: забыть, что вход по initData уже был. */
export function resetLaunchLoginForTests(): void {
  launchLoginDone = false;
}

export function useMe() {
  return useQuery({
    queryKey: ME_QUERY_KEY,
    queryFn: fetchMe,
    retry: false, // 401 не повторяем: пользователь просто не вошёл
    staleTime: ME_STALE_TIME_MS,
  });
}

/** Вход через Telegram Mini App: initData → сессия (cookie) → Me. */
export function useTelegramLogin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (initData: string) =>
      unwrap(await api.POST("/api/v1/auth/telegram", { body: { init_data: initData } })),
    onSuccess: (me) => {
      launchLoginDone = true;
      queryClient.setQueryData(ME_QUERY_KEY, me);
    },
  });
}

/** Вход по одноразовой ссылке: токен гасится ТОЛЬКО этим POST-запросом. */
export function useLinkLogin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (token: string) =>
      unwrap(await api.POST("/api/v1/auth/link", { body: { token } })),
    onSuccess: (me) => {
      queryClient.setQueryData(ME_QUERY_KEY, me);
    },
  });
}

/** Выход: сессия удаляется на сервере, кеш запросов очищается. */
export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      unwrapEmpty(await api.POST("/api/v1/auth/logout"));
    },
    onSuccess: () => {
      queryClient.clear();
    },
  });
}
