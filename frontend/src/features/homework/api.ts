/** Запросы ДЗ для персонала (docs/08 §5.5, §6). Мутации сбрасывают кеши заданий и выдач. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/api/client";
import { unwrap } from "@/api/errors";
import type { components } from "@/api/schema";

export type HomeworkCreate = components["schemas"]["HomeworkCreate"];
export type HomeworkItem = components["schemas"]["HomeworkItem"];
export type HomeworkListItem = components["schemas"]["HomeworkListItem"];
export type AssignmentRow = components["schemas"]["AdminAssignmentItem"];
export type AssignmentDetail = components["schemas"]["AdminAssignmentDetail"];
export type AssignmentFile = components["schemas"]["HomeworkFileItem"];
export type GradeRequest = components["schemas"]["GradeRequest"];
export type ReturnRequest = components["schemas"]["ReturnRequest"];
export type ExtendRequest = components["schemas"]["ExtendRequest"];

export const PAGE_SIZE = 50;
/** Сколько раз можно переносить срок (docs/04 §5.4). */
export const MAX_EXTENSIONS = 2;

const HOMEWORK_KEY = ["homework"] as const;
const ASSIGNMENTS_KEY = ["assignments"] as const;

export function useHomeworkList(limit: number) {
  return useQuery({
    queryKey: [...HOMEWORK_KEY, "list", limit],
    queryFn: async () =>
      unwrap(await api.GET("/api/v1/admin/homework", { params: { query: { limit, offset: 0 } } })),
    placeholderData: (previous) => previous,
  });
}

export function useHomework(homeworkId: number) {
  return useQuery({
    queryKey: [...HOMEWORK_KEY, homeworkId],
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/admin/homework/{homework_id}", {
          params: { path: { homework_id: homeworkId } },
        }),
      ),
  });
}

export function useReviewQueue(limit: number) {
  return useQuery({
    queryKey: [...ASSIGNMENTS_KEY, "queue", limit],
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/admin/assignments/review-queue", {
          params: { query: { limit, offset: 0 } },
        }),
      ),
    placeholderData: (previous) => previous,
  });
}

export function useAssignment(assignmentId: number) {
  return useQuery({
    queryKey: [...ASSIGNMENTS_KEY, assignmentId],
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/admin/assignments/{assignment_id}", {
          params: { path: { assignment_id: assignmentId } },
        }),
      ),
  });
}

/** Подписанная ссылка на файл выдачи; живёт 10 минут, поэтому кешируем её недолго. */
export function useFileUrl(fileId: number) {
  return useQuery({
    queryKey: ["file-url", fileId],
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/files/{file_id}/url", { params: { path: { file_id: fileId } } }),
      ),
    staleTime: 5 * 60_000,
  });
}

function useInvalidateAll() {
  const queryClient = useQueryClient();
  return async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: HOMEWORK_KEY }),
      queryClient.invalidateQueries({ queryKey: ASSIGNMENTS_KEY }),
    ]);
  };
}

/** Тело multipart: openapi-fetch сам уберёт Content-Type, и браузер поставит границу. */
function multipart(file: File): { body: { file: string }; bodySerializer: () => FormData } {
  const form = new FormData();
  form.append("file", file);
  return { body: { file: file.name }, bodySerializer: () => form };
}

export function useCreateHomework() {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: async (body: HomeworkCreate) =>
      unwrap(await api.POST("/api/v1/admin/homework", { body })),
    onSuccess: invalidate,
  });
}

export function useUploadMaterial() {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: async (input: { homeworkId: number; file: File }) =>
      unwrap(
        await api.POST("/api/v1/admin/homework/{homework_id}/materials", {
          params: { path: { homework_id: input.homeworkId } },
          ...multipart(input.file),
        }),
      ),
    onSuccess: invalidate,
  });
}

export function useGrade(assignmentId: number) {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: async (body: GradeRequest) =>
      unwrap(
        await api.POST("/api/v1/admin/assignments/{assignment_id}/grade", {
          params: { path: { assignment_id: assignmentId } },
          body,
        }),
      ),
    onSuccess: invalidate,
  });
}

export function useReturn(assignmentId: number) {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: async (body: ReturnRequest) =>
      unwrap(
        await api.POST("/api/v1/admin/assignments/{assignment_id}/return", {
          params: { path: { assignment_id: assignmentId } },
          body,
        }),
      ),
    onSuccess: invalidate,
  });
}

export function useExtend(assignmentId: number) {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: async (body: ExtendRequest) =>
      unwrap(
        await api.POST("/api/v1/admin/assignments/{assignment_id}/extend", {
          params: { path: { assignment_id: assignmentId } },
          body,
        }),
      ),
    onSuccess: invalidate,
  });
}

export function useUploadReviewFile(assignmentId: number) {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: async (file: File) =>
      unwrap(
        await api.POST("/api/v1/admin/assignments/{assignment_id}/review-files", {
          params: { path: { assignment_id: assignmentId } },
          ...multipart(file),
        }),
      ),
    onSuccess: invalidate,
  });
}
