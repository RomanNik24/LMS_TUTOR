/**
 * Запросы аутентификации (docs/12 §5.3). Запросы к API живут только в api.ts возможностей (features).
 * Данные о пользователе хранит TanStack Query под ключом ["me"].
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/api/client";
import { unwrap, unwrapEmpty } from "@/api/errors";
import type { components } from "@/api/schema";

export type Me = components["schemas"]["MeResponse"];
export type Role = Me["role"];

export const ME_QUERY_KEY = ["me"] as const;

const ME_STALE_TIME_MS = 5 * 60_000;

export function useMe() {
  return useQuery({
    queryKey: ME_QUERY_KEY,
    queryFn: async () => unwrap(await api.GET("/api/v1/me")),
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
