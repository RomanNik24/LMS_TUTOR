/**
 * Справочники (docs/08 §3). Предметы — данные в БД (docs/06 A4), поэтому их список и названия
 * приходят с сервера, а не записаны в коде фронтенда.
 */
import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import { unwrap } from "@/api/errors";
import type { components } from "@/api/schema";

export type Subject = components["schemas"]["SubjectItem"];

// Справочник меняется редко: загружаем его один раз за сеанс (staleTime: Infinity).
// Все экраны берут данные из общего кеша TanStack Query по одному ключу — повторных запросов нет.
const SUBJECTS_KEY = ["reference", "subjects"] as const;

export function useSubjects() {
  return useQuery({
    queryKey: SUBJECTS_KEY,
    queryFn: async () => unwrap(await api.GET("/api/v1/reference/subjects")),
    staleTime: Infinity,
  });
}

/**
 * Функция «код предмета → название» для подписей в списках и карточках.
 * Пока справочник загружается (или если предмет уже отключён), показывает сам код.
 */
export function useSubjectName(): (code: string) => string {
  const { data } = useSubjects();
  return (code) => data?.find((subject) => subject.code === code)?.name ?? code;
}

export type ExamType = components["schemas"]["ExamTypeItem"];

const EXAM_TYPES_KEY = ["reference", "exam-types"] as const;

/** Типы экзаменов (4 штуки на MVP): форма пробника и подписи к результатам. */
export function useExamTypes() {
  return useQuery({
    queryKey: EXAM_TYPES_KEY,
    queryFn: async () => unwrap(await api.GET("/api/v1/reference/exam-types")),
    staleTime: Infinity,
  });
}
