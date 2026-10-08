/**
 * Отчёты по ученику (docs/08 §4, §5.2). Все числа считает сервер (docs/04 §11): фронтенд только
 * выбирает период и рисует.
 */
import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import { unwrap } from "@/api/errors";
import type { components } from "@/api/schema";
import { dayStartUtcIso, shiftDayKey, todayKey } from "@/lib/datetime";

export type StudentReport = components["schemas"]["StudentReport"];

export type ReportPeriod = "weeks4" | "months3" | "all";

/** Длина периода в днях; «всё» ограничено годом (docs/08 §1: период не больше 1 года). */
const PERIOD_DAYS: Record<ReportPeriod, number> = { weeks4: 28, months3: 91, all: 365 };

/** Границы периода `[from, to)` в UTC: от начала дня N дней назад до начала завтрашнего дня. */
export function periodRange(period: ReportPeriod, timeZone: string): { from: string; to: string } {
  const today = todayKey(timeZone);
  return {
    from: dayStartUtcIso(shiftDayKey(today, -PERIOD_DAYS[period]), timeZone),
    to: dayStartUtcIso(shiftDayKey(today, 1), timeZone),
  };
}

/** Собственный отчёт ученика (`/student/reports`). */
export function useMyReport(period: ReportPeriod, timeZone: string) {
  const range = periodRange(period, timeZone);
  return useQuery({
    queryKey: ["reports", "me", range.from, range.to],
    queryFn: async () =>
      unwrap(await api.GET("/api/v1/student/reports", { params: { query: range } })),
  });
}

/** Отчёт ученика для персонала (`/admin/students/{id}/report`). */
export function useAdminStudentReport(studentId: number, period: ReportPeriod, timeZone: string) {
  const range = periodRange(period, timeZone);
  return useQuery({
    queryKey: ["reports", "student", studentId, range.from, range.to],
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/admin/students/{student_id}/report", {
          params: { path: { student_id: studentId }, query: range },
        }),
      ),
  });
}
