/**
 * Дашборд «Сегодня» (docs/08 §5.1). Сервер отдаёт владельцу схему с `earned_month` и
 * `expected_month`, менеджеру — схему без денег: фронтенд ничего не скрывает условием, а просто
 * рисует то, что пришло.
 */
import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import { unwrap } from "@/api/errors";
import type { components } from "@/api/schema";

export type DashboardStaff = components["schemas"]["DashboardStaff"];
export type DashboardOwner = components["schemas"]["DashboardOwner"];
export type TodayDashboard = DashboardOwner | DashboardStaff;
export type DashboardLesson = components["schemas"]["DashboardLesson"];
export type DashboardAssignmentItem = components["schemas"]["DashboardAssignmentItem"];

/** Есть ли в ответе заработок месяца (только владелец). */
export function isOwnerDashboard(data: TodayDashboard): data is DashboardOwner {
  return "earned_month" in data;
}

export const DASHBOARD_KEY = ["dashboard", "today"] as const;

export function useTodayDashboard() {
  return useQuery({
    queryKey: DASHBOARD_KEY,
    queryFn: async () => unwrap(await api.GET("/api/v1/admin/dashboard/today")),
    refetchOnWindowFocus: true,
  });
}
