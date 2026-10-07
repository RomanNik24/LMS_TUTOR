/** Запросы расписания для персонала (docs/08 §5.4). Мутации сбрасывают кеш уроков. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/api/client";
import { unwrap } from "@/api/errors";
import type { components } from "@/api/schema";

export type Lesson = components["schemas"]["LessonItem"];
export type LessonStatus = components["schemas"]["LessonStatus"];
export type Attendance = components["schemas"]["LessonParticipantItem"]["attendance"];
export type LessonCreate = components["schemas"]["LessonCreate"];
export type LessonReschedule = components["schemas"]["LessonReschedule"];
export type LessonCancel = components["schemas"]["LessonCancel"];
export type LessonComplete = components["schemas"]["LessonComplete"];
export type TemplateCreate = components["schemas"]["TemplateCreate"];

const KEY = ["lessons"] as const;
const LESSONS_LIMIT = 200;

export type LessonsRange = {
  /** Начало периода, ISO UTC (включительно). */
  from: string;
  /** Конец периода, ISO UTC (не включительно). */
  to: string;
  studentId: number | null;
  status: LessonStatus | null;
};

export function useLessons(range: LessonsRange) {
  return useQuery({
    queryKey: [...KEY, range],
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/admin/lessons", {
          params: {
            query: {
              from: range.from,
              to: range.to,
              student_id: range.studentId,
              status: range.status,
              limit: LESSONS_LIMIT,
              offset: 0,
            },
          },
        }),
      ),
    placeholderData: (previous) => previous,
  });
}

function useInvalidate() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: KEY });
}

export function useCreateLesson() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: async (body: LessonCreate) =>
      unwrap(await api.POST("/api/v1/admin/lessons", { body })),
    onSuccess: invalidate,
  });
}

export function useRescheduleLesson(lessonId: number) {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: async (body: LessonReschedule) =>
      unwrap(
        await api.POST("/api/v1/admin/lessons/{lesson_id}/reschedule", {
          params: { path: { lesson_id: lessonId } },
          body,
        }),
      ),
    onSuccess: invalidate,
  });
}

export function useCancelLesson(lessonId: number) {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: async (body: LessonCancel) =>
      unwrap(
        await api.POST("/api/v1/admin/lessons/{lesson_id}/cancel", {
          params: { path: { lesson_id: lessonId } },
          body,
        }),
      ),
    onSuccess: invalidate,
  });
}

export function useCompleteLesson(lessonId: number) {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: async (body: LessonComplete) =>
      unwrap(
        await api.POST("/api/v1/admin/lessons/{lesson_id}/complete", {
          params: { path: { lesson_id: lessonId } },
          body,
        }),
      ),
    onSuccess: invalidate,
  });
}

export function useCreateTemplate() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: async (body: TemplateCreate) =>
      unwrap(await api.POST("/api/v1/admin/schedule-templates", { body })),
    onSuccess: invalidate,
  });
}
