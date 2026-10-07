/** Запросы расписания ученика (docs/08 §4): только свои уроки. */
import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import { unwrap } from "@/api/errors";
import type { components } from "@/api/schema";

export type StudentLesson = components["schemas"]["StudentLessonItem"];

export function useStudentLessons(from: string, to: string) {
  return useQuery({
    queryKey: ["student-lessons", from, to],
    queryFn: async () =>
      unwrap(await api.GET("/api/v1/student/lessons", { params: { query: { from, to } } })),
  });
}

export function useStudentLesson(lessonId: number) {
  return useQuery({
    queryKey: ["student-lessons", "card", lessonId],
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/student/lessons/{lesson_id}", {
          params: { path: { lesson_id: lessonId } },
        }),
      ),
    retry: false,
  });
}
