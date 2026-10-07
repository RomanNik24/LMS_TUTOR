/** Запросы раздела «Ученики» (docs/08 §5.2). Мутации сбрасывают кеш списка и карточки. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/api/client";
import { unwrap, unwrapEmpty } from "@/api/errors";
import type { components } from "@/api/schema";

export type StudentCard =
  | components["schemas"]["StudentCardOwner"]
  | components["schemas"]["StudentCardManager"];
export type StudentListItem = components["schemas"]["StudentListItem"];
export type StudentStatus = components["schemas"]["StudentStatus"];
type StudentCreate = components["schemas"]["StudentCreate"];
type StudentUpdate = components["schemas"]["StudentUpdate"];

export const PAGE_SIZE = 20;
const KEY = ["students"] as const;

export type StudentsFilter = { status: StudentStatus; q: string; limit: number };

export function useStudents(filter: StudentsFilter) {
  const q = filter.q.trim();
  return useQuery({
    queryKey: [...KEY, "list", filter.status, q, filter.limit],
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/admin/students", {
          params: {
            query: {
              status: filter.status,
              q: q === "" ? null : q,
              limit: filter.limit,
              offset: 0,
            },
          },
        }),
      ),
    placeholderData: (previous) => previous,
  });
}

export function useStudent(id: number) {
  return useQuery({
    queryKey: [...KEY, "card", id],
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/admin/students/{student_id}", {
          params: { path: { student_id: id } },
        }),
      ),
  });
}

function useInvalidate() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: KEY });
}

export function useCreateStudent() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: async (body: StudentCreate) =>
      unwrap(await api.POST("/api/v1/admin/students", { body })),
    onSuccess: invalidate,
  });
}

export function useUpdateStudent(id: number) {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: async (body: StudentUpdate) =>
      unwrap(
        await api.PATCH("/api/v1/admin/students/{student_id}", {
          params: { path: { student_id: id } },
          body,
        }),
      ),
    onSuccess: invalidate,
  });
}

export function useArchiveStudent(id: number) {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: async () =>
      unwrap(
        await api.POST("/api/v1/admin/students/{student_id}/archive", {
          params: { path: { student_id: id } },
        }),
      ),
    onSuccess: invalidate,
  });
}

export function useRestoreStudent(id: number) {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: async () =>
      unwrap(
        await api.POST("/api/v1/admin/students/{student_id}/restore", {
          params: { path: { student_id: id } },
        }),
      ),
    onSuccess: invalidate,
  });
}

export function useUnlinkTelegram(id: number) {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: async () => {
      unwrapEmpty(
        await api.POST("/api/v1/admin/students/{student_id}/unlink-telegram", {
          params: { path: { student_id: id } },
        }),
      );
    },
    onSuccess: invalidate,
  });
}
