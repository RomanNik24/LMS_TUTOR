import { screen, within } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { texts } from "@/lib/texts";
import { routes } from "@/router";
import { mockMe } from "@/test/mockMe";
import { renderRoutes } from "@/test/renderRoutes";
import { server } from "@/test/server";

const t = texts.admin.dashboard;

const NOW = new Date("2026-10-14T10:00:00Z");

const EMPTY = { total: 0, items: [] };

const staffDashboard = (patch: Record<string, unknown> = {}) => ({
  date: "2026-10-14",
  timezone: "Europe/Moscow",
  lessons: EMPTY,
  review_queue: EMPTY,
  unsubmitted: EMPTY,
  unmarked_lessons: EMPTY,
  deadlines: EMPTY,
  ...patch,
});

const assignment = (id: number, name: string, title: string) => ({
  assignment_id: id,
  student_id: 20 + id,
  student_name: name,
  title,
  status: "assigned",
  due_at: "2026-10-14T15:00:00Z",
});

function mockDashboard(body: Record<string, unknown>) {
  server.use(http.get("*/api/v1/admin/dashboard/today", () => HttpResponse.json(body)));
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"], now: NOW });
});
afterEach(() => {
  vi.useRealTimers();
});

describe("Дашборд «Сегодня»", () => {
  it("владелец видит заработано и ожидается; блоки ведут к работам; сводка в герое", async () => {
    mockMe("owner");
    mockDashboard(
      staffDashboard({
        earned_month: 12500,
        expected_month: 8000,
        lessons: {
          total: 2,
          items: [
            {
              id: 1,
              subject_code: "informatics",
              start_at: "2026-10-14T07:00:00Z",
              end_at: "2026-10-14T08:00:00Z",
              status: "scheduled",
              student_names: ["Аня"],
              needs_mark: true,
            },
            {
              id: 2,
              subject_code: "math",
              start_at: "2026-10-14T14:00:00Z",
              end_at: "2026-10-14T15:00:00Z",
              status: "scheduled",
              student_names: ["Аня", "Борис"],
              needs_mark: false,
            },
          ],
        },
        review_queue: {
          total: 7,
          items: [{ assignment_id: 5, student_name: "Вера", title: "Графы", submitted_at: null }],
        },
        unsubmitted: { total: 1, items: [assignment(9, "Борис", "Сети")] },
      }),
    );
    renderRoutes(routes, ["/admin/today"]);

    expect(await screen.findByText(t.earnedTitle)).toBeInTheDocument();
    expect(screen.getByText(/12\s500\s₽/)).toBeInTheDocument();
    expect(screen.getByText(/ожидается\s8\s000\s₽/)).toBeInTheDocument();
    expect(screen.getByText(/2 урока · 7 на проверке/)).toBeInTheDocument();
    expect(screen.getByText(t.lessonsMark)).toBeInTheDocument();
    expect(screen.getByText(t.more(6))).toBeInTheDocument();
    const queue = screen.getByRole("link", { name: /Вера/ });
    expect(queue).toHaveAttribute("href", "/admin/assignments/5");
    const unsubmitted = screen.getByRole("link", { name: /Борис\s+Сети/ });
    expect(unsubmitted).toHaveAttribute("href", "/admin/assignments/9");
  });

  it("пустые блоки показывают «Всё в порядке»", async () => {
    mockMe("owner");
    mockDashboard(staffDashboard({ earned_month: 0, expected_month: 0 }));
    renderRoutes(routes, ["/admin/today"]);

    expect(await screen.findAllByText(t.allGood)).toHaveLength(5);
    expect(screen.getByText(/Уроков нет · 0 на проверке/)).toBeInTheDocument();
  });

  it("у менеджера нет ни заработка, ни рублей, ни пункта «Финансы»", async () => {
    mockMe("manager");
    mockDashboard(
      staffDashboard({
        review_queue: {
          total: 1,
          items: [{ assignment_id: 5, student_name: "Вера", title: "Графы", submitted_at: null }],
        },
      }),
    );
    renderRoutes(routes, ["/admin/today"]);

    await screen.findByRole("link", { name: /Вера/ });
    expect(screen.queryByText(t.earnedTitle)).toBeNull();
    expect(document.body.textContent).not.toMatch(/₽|заработано|ожидается/i);
    expect(screen.queryByRole("link", { name: texts.nav.admin.finance })).toBeNull();
  });

  it("ошибка загрузки: сообщение и «Повторить»", async () => {
    mockMe("owner");
    server.use(
      http.get("*/api/v1/admin/dashboard/today", () =>
        HttpResponse.json(
          { error: { code: "internal_error", message: "x", details: {} } },
          { status: 500 },
        ),
      ),
    );
    renderRoutes(routes, ["/admin/today"]);

    const alert = await screen.findByRole("alert");
    expect(within(alert).getByRole("button")).toBeInTheDocument();
  });
});
