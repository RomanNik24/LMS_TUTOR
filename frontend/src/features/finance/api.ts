/**
 * Финансы и статистика (docs/08 §5.8), только владелец. Суммы считает сервер; здесь — выбор
 * периода, запросы и выгрузка CSV.
 */
import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import { toApiError, unwrap } from "@/api/errors";
import type { components } from "@/api/schema";
import { dayStartUtcIso, daysBetween, shiftDayKey, todayKey, weekStartKey } from "@/lib/datetime";

export type EarningsReport = components["schemas"]["EarningsReport"];
export type EarningsRow = components["schemas"]["EarningsRow"];
export type CancellationStats = components["schemas"]["CancellationStats"];
export type EarningsGroupBy = components["schemas"]["EarningsGroupBy"];

export type PeriodMode = "week" | "month" | "custom";
export type CustomRange = { from: string; to: string };
export type DateRange = { from: string; to: string };

/** Не больше года (docs/08 §1). */
export const MAX_PERIOD_DAYS = 366;

/** Первое число следующего месяца для ключа дня `yyyy-MM-dd`. */
function nextMonthStart(dayKey: string): string {
  const first = `${dayKey.slice(0, 8)}01`;
  return `${shiftDayKey(first, 32).slice(0, 8)}01`;
}

/**
 * Границы периода `[from, to)` в UTC по выбранному режиму. Для «своего периода» `custom` — даты
 * `yyyy-MM-dd` включительно; `null`, если даты неверны (конец раньше начала или больше года).
 */
export function periodRange(
  mode: PeriodMode,
  custom: CustomRange,
  timeZone: string,
): DateRange | null {
  const today = todayKey(timeZone);
  let firstDay: string;
  let afterLastDay: string;
  if (mode === "week") {
    firstDay = weekStartKey(today);
    afterLastDay = shiftDayKey(firstDay, 7);
  } else if (mode === "month") {
    firstDay = `${today.slice(0, 8)}01`;
    afterLastDay = nextMonthStart(today);
  } else {
    if (custom.from === "" || custom.to === "") return null;
    firstDay = custom.from;
    afterLastDay = shiftDayKey(custom.to, 1);
    const days = daysBetween(firstDay, afterLastDay);
    if (days <= 0 || days > MAX_PERIOD_DAYS) return null;
  }
  return { from: dayStartUtcIso(firstDay, timeZone), to: dayStartUtcIso(afterLastDay, timeZone) };
}

export function useEarnings(range: DateRange | null, groupBy: EarningsGroupBy) {
  return useQuery({
    queryKey: ["finance", "earnings", range, groupBy],
    enabled: range !== null,
    placeholderData: keepPreviousData,
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/admin/finance/earnings", {
          params: { query: { ...(range as DateRange), group_by: groupBy } },
        }),
      ),
  });
}

export function useCancellations(range: DateRange | null) {
  return useQuery({
    queryKey: ["finance", "cancellations", range],
    enabled: range !== null,
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/admin/stats/cancellations", {
          params: { query: range as DateRange },
        }),
      ),
  });
}

/** Скачивает CSV за период: запрос с cookie сессии, файл отдаётся браузеру ссылкой на blob. */
export async function downloadEarningsCsv(range: DateRange, fileName: string): Promise<void> {
  const result = await api.GET("/api/v1/admin/finance/export.csv", {
    params: { query: range },
    parseAs: "blob",
  });
  if (result.error !== undefined || result.data === undefined) throw toApiError(result);
  const url = URL.createObjectURL(result.data);
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
