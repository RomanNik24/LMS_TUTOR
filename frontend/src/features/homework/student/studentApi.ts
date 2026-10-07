/** Запросы ДЗ ученика (docs/08 §4, §6). Загрузка файла идёт через XHR ради прогресса. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, CSRF_HEADERS } from "@/api/client";
import { ApiError, parseErrorBody, unwrap, unwrapEmpty } from "@/api/errors";
import type { components } from "@/api/schema";

export type StudentHomeworkFilter = "active" | "submitted" | "graded" | "expired";
export type StudentAssignment = components["schemas"]["StudentAssignmentItem"];
export type StudentAssignmentDetail = components["schemas"]["StudentAssignmentDetail"];
export type SolutionFile = components["schemas"]["HomeworkFileItem"];

export const PAGE_SIZE = 50;
/** Лимиты загрузки (docs/09): совпадают с серверными, сервер проверяет их окончательно. */
export const MAX_FILES = 10;
export const MAX_FILE_BYTES = 10 * 1024 * 1024;

const KEY = ["student-homework"] as const;

export function useStudentHomework(filter: StudentHomeworkFilter, limit: number) {
  return useQuery({
    queryKey: [...KEY, "list", filter, limit],
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/student/homework", {
          params: { query: { status: filter, limit, offset: 0 } },
        }),
      ),
    placeholderData: (previous) => previous,
  });
}

export function useStudentAssignment(assignmentId: number) {
  return useQuery({
    queryKey: [...KEY, assignmentId],
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/student/homework/{assignment_id}", {
          params: { path: { assignment_id: assignmentId } },
        }),
      ),
  });
}

function useInvalidate() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: KEY });
}

/** Загрузка одного файла с прогрессом (fetch не умеет сообщать о ходе отправки). */
export function uploadSolution(
  assignmentId: number,
  file: File,
  onProgress: (percent: number) => void,
): Promise<SolutionFile> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    const url = `${window.location.origin}/api/v1/student/homework/${String(assignmentId)}/files`;
    request.open("POST", url);
    request.withCredentials = true;
    for (const [name, value] of Object.entries(CSRF_HEADERS)) request.setRequestHeader(name, value);
    request.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(Math.round((event.loaded / event.total) * 100));
    };
    request.onerror = () => {
      reject(new TypeError("network"));
    };
    request.onload = () => {
      let body: unknown = null;
      try {
        body = JSON.parse(request.responseText);
      } catch {
        body = null;
      }
      if (request.status >= 200 && request.status < 300) {
        resolve(body as SolutionFile);
        return;
      }
      const { code, message } = parseErrorBody(body);
      reject(new ApiError(request.status, code, message));
    };
    const form = new FormData();
    form.append("file", file);
    request.send(form);
  });
}

export function useUploadSolution(assignmentId: number) {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: async (input: { file: File; onProgress: (percent: number) => void }) =>
      uploadSolution(assignmentId, input.file, input.onProgress),
    onSuccess: invalidate,
  });
}

export function useDeleteSolution(assignmentId: number) {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: async (fileId: number) =>
      unwrapEmpty(
        await api.DELETE("/api/v1/student/homework/{assignment_id}/files/{file_id}", {
          params: { path: { assignment_id: assignmentId, file_id: fileId } },
        }),
      ),
    onSuccess: invalidate,
  });
}

export function useSubmitHomework(assignmentId: number) {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: async (studentComment: string | null) =>
      unwrap(
        await api.POST("/api/v1/student/homework/{assignment_id}/submit", {
          params: { path: { assignment_id: assignmentId } },
          body: { student_comment: studentComment },
        }),
      ),
    onSuccess: invalidate,
  });
}

export function useSelfReport(assignmentId: number) {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: async (studentComment: string | null) =>
      unwrap(
        await api.POST("/api/v1/student/homework/{assignment_id}/self-report", {
          params: { path: { assignment_id: assignmentId } },
          body: { student_comment: studentComment },
        }),
      ),
    onSuccess: invalidate,
  });
}

/** Ссылка на материал задания: подписанный URL запрашивается по клику. */
export async function materialUrl(materialId: number): Promise<string> {
  const data = unwrap(
    await api.GET("/api/v1/files/materials/{material_id}/url", {
      params: { path: { material_id: materialId } },
    }),
  );
  return data.url;
}
