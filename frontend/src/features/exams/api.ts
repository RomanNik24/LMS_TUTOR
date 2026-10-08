/** Запросы раздела «Пробники» (docs/08 §5.6). Конвертацию баллов считает сервер. */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/api/client";
import { unwrap, unwrapEmpty } from "@/api/errors";
import type { components } from "@/api/schema";

export type MockExam = components["schemas"]["MockExamItem"];
export type MockExamCreate = components["schemas"]["MockExamCreate"];
export type ScoreConversion = components["schemas"]["ScoreConversion"];
export type ConvertRequest = components["schemas"]["ConvertRequest"];

export const PAGE_SIZE = 20;
const KEY = ["mock-exams"] as const;

export type ExamsFilter = { studentId: number | null; examTypeId: number | null; limit: number };

export function useMockExams(filter: ExamsFilter) {
  return useQuery({
    queryKey: [...KEY, "list", filter.studentId, filter.examTypeId, filter.limit],
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/admin/mock-exams", {
          params: {
            query: {
              student_id: filter.studentId,
              exam_type_id: filter.examTypeId,
              limit: filter.limit,
              offset: 0,
            },
          },
        }),
      ),
    placeholderData: keepPreviousData,
  });
}

/**
 * Предпросмотр конвертации в форме: запрос идёт, только когда `request` не `null`
 * (все поля формы корректны). Результат кешируется по значениям полей.
 */
export function useConversionPreview(request: ConvertRequest | null) {
  return useQuery({
    queryKey: [...KEY, "convert", request],
    enabled: request !== null,
    queryFn: async () =>
      unwrap(
        await api.POST("/api/v1/admin/mock-exams/convert", {
          body: request as ConvertRequest, // enabled: запрос выполняется только при request !== null
        }),
      ),
    placeholderData: keepPreviousData,
    retry: false,
  });
}

export function useCreateMockExam() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: MockExamCreate) =>
      unwrap(await api.POST("/api/v1/admin/mock-exams", { body })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: KEY }),
  });
}

export function useDeleteMockExam() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (resultId: number) =>
      unwrapEmpty(
        await api.DELETE("/api/v1/admin/mock-exams/{result_id}", {
          params: { path: { result_id: resultId } },
        }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: KEY }),
  });
}
