/** Запросы раздела «Каталог услуг» (docs/08 §5.7). Порядок и публикацию хранит сервер. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/api/client";
import { unwrap, unwrapEmpty } from "@/api/errors";
import type { components } from "@/api/schema";

export type CatalogItem = components["schemas"]["CatalogItemAdmin"];
export type CatalogCreate = components["schemas"]["CatalogCreate"];
export type CatalogUpdate = components["schemas"]["CatalogUpdate"];

const KEY = ["catalog"] as const;

export function useCatalog() {
  return useQuery({
    queryKey: KEY,
    queryFn: async () => unwrap(await api.GET("/api/v1/admin/catalog")),
  });
}

export function useCreateCatalogItem() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: CatalogCreate) =>
      unwrap(await api.POST("/api/v1/admin/catalog", { body })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: KEY }),
  });
}

export function useUpdateCatalogItem() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, body }: { id: number; body: CatalogUpdate }) =>
      unwrap(
        await api.PATCH("/api/v1/admin/catalog/{item_id}", {
          params: { path: { item_id: id } },
          body,
        }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: KEY }),
  });
}

export function useReorderCatalog() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (ids: number[]) =>
      unwrap(await api.PUT("/api/v1/admin/catalog/order", { body: { ids } })),
    onSuccess: (items) => queryClient.setQueryData(KEY, items),
  });
}

export function useDeleteCatalogItem() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: number) =>
      unwrapEmpty(
        await api.DELETE("/api/v1/admin/catalog/{item_id}", {
          params: { path: { item_id: id } },
        }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: KEY }),
  });
}

/** Порядок идентификаторов после переноса карточки с позиции `from` на позицию `to`. */
export function movedIds(items: readonly CatalogItem[], from: number, to: number): number[] {
  const ids = items.map((item) => item.id);
  const [moved] = ids.splice(from, 1);
  if (moved === undefined) return ids;
  ids.splice(to, 0, moved);
  return ids;
}
