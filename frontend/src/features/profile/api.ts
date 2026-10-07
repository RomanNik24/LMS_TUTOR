/** Запрос профиля: PATCH /me (имя и часовой пояс). Ответ кладётся в кеш «me». */
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api } from "@/api/client";
import { unwrap } from "@/api/errors";
import type { components } from "@/api/schema";
import { ME_QUERY_KEY } from "@/features/auth/api";

type MeUpdate = components["schemas"]["MeUpdateRequest"];

export function useUpdateMe() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: MeUpdate) => unwrap(await api.PATCH("/api/v1/me", { body })),
    onSuccess: (me) => {
      queryClient.setQueryData(ME_QUERY_KEY, me);
    },
  });
}
