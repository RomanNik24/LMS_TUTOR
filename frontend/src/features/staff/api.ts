/** Запросы раздела «Сотрудники» (docs/08 §5.3), только владелец. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/api/client";
import { unwrap } from "@/api/errors";
import type { components } from "@/api/schema";

export type StaffItem = components["schemas"]["StaffItem"];
type StaffCreate = components["schemas"]["StaffCreate"];
type StaffUpdate = components["schemas"]["StaffUpdate"];

const KEY = ["staff"] as const;
const LIST_LIMIT = 200;

export function useStaff(includeArchived: boolean) {
  return useQuery({
    queryKey: [...KEY, includeArchived],
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/admin/staff", {
          params: { query: { include_archived: includeArchived, limit: LIST_LIMIT, offset: 0 } },
        }),
      ),
  });
}

function useInvalidate() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: KEY });
}

export function useCreateStaff() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: async (body: StaffCreate) =>
      unwrap(await api.POST("/api/v1/admin/staff", { body })),
    onSuccess: invalidate,
  });
}

export function useUpdateStaff(id: number) {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: async (body: StaffUpdate) =>
      unwrap(
        await api.PATCH("/api/v1/admin/staff/{staff_id}", {
          params: { path: { staff_id: id } },
          body,
        }),
      ),
    onSuccess: invalidate,
  });
}

export function useArchiveStaff() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: async (id: number) =>
      unwrap(
        await api.POST("/api/v1/admin/staff/{staff_id}/archive", {
          params: { path: { staff_id: id } },
        }),
      ),
    onSuccess: invalidate,
  });
}
