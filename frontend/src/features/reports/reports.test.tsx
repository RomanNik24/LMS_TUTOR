import { fireEvent, screen, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { texts } from "@/lib/texts";
import { routes } from "@/router";
import { mockMe } from "@/test/mockMe";
import { renderRoutes } from "@/test/renderRoutes";
import { server } from "@/test/server";

const t = texts.student.reports;

const NOW = new Date("2026-10-14T12:00:00Z");
const DAY_MS = 86_400_000;

const report = (patch: Record<string, unknown> = {}) => ({
  student_id: 5,
  timezone: "Europe/Moscow",
  homework_weekly: [
    { week_start: "2026-10-05", average_percent: 70, graded_count: 2 },
    { week_start: "2026-10-12", average_percent: 85, graded_count: 1 },
  ],
  homework_last_percent: 85,
  on_time: { on_time_count: 2, total_count: 4, percent: 50 },
  mock_exams: [
    {
      exam_date: "2026-10-03",
      exam_type_code: "ege_informatics",
      exam_type_name: "ЕГЭ — Информатика",
      result_kind: "test_100",
      primary_score: 20,
      max_primary: 27,
      converted_value: null,
      scale_applicable: false,
      percent: 74,
    },
    {
      exam_date: "2026-10-10",
      exam_type_code: "ege_informatics",
      exam_type_name: "ЕГЭ — Информатика",
      result_kind: "test_100",
      primary_score: 20,
      max_primary: 29,
      converted_value: 78,
      scale_applicable: true,
      percent: 69,
    },
  ],
  attendance: { attended: 3, no_show: 0, cancelled: 0, pending: 1 },
  ...patch,
});

let lastQuery: URLSearchParams | null = null;

function mockReport(body: unknown, path = "*/api/v1/student/reports") {
  server.use(
    http.get(path, ({ request }) => {
      lastQuery = new URL(request.url).searchParams;
      return HttpResponse.json(body as Record<string, unknown>);
    }),
  );
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"], now: NOW });
  lastQuery = null;
});
afterEach(() => {
  vi.useRealTimers();
});

describe("Отчёты ученика", () => {
  it("графики с текстовой сводкой: последний результат, недели, пробники, «сдано в срок»", async () => {
    mockMe("student", "Аня");
    mockReport(report());
    renderRoutes(routes, ["/app/reports"]);
    expect(await screen.findByText(t.homework.last(85))).toBeInTheDocument();
    // текстовая сводка дублирует графики (доступность, docs/07 §10)
    expect(screen.getByText(t.homework.weekPoint("пн, 5 окт", 70, 2))).toBeInTheDocument();
    expect(screen.getByText(t.homework.weekPoint("пн, 12 окт", 85, 1))).toBeInTheDocument();
    expect(
      screen.getByText(
        t.mock.point("сб, 3 окт", "ЕГЭ — Информатика", `${texts.exams.notApplicable} (74%)`),
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        t.mock.point("сб, 10 окт", "ЕГЭ — Информатика", `${texts.exams.testLabel(78)} (69%)`),
      ),
    ).toBeInTheDocument();
    expect(screen.getByText(t.onTime.value(50))).toBeInTheDocument();
    expect(screen.getByText(t.onTime.detail(2, 4))).toBeInTheDocument();
    expect(screen.getAllByRole("img", { name: t.homework.title })).toHaveLength(1);
  });

  it("период по умолчанию — 4 недели в поясе ученика; «3 месяца» и «Всё» меняют запрос", async () => {
    mockMe("student");
    mockReport(report());
    renderRoutes(routes, ["/app/reports"]);
    await screen.findByText(t.homework.last(85));
    const span = () => {
      const from = Date.parse(lastQuery?.get("from") ?? "");
      const to = Date.parse(lastQuery?.get("to") ?? "");
      return Math.round((to - from) / DAY_MS);
    };
    expect(span()).toBe(29); // 28 дней назад … начало завтрашнего дня
    fireEvent.mouseDown(screen.getByRole("tab", { name: t.periods.months3 }), { button: 0 });
    await waitFor(() => {
      expect(span()).toBe(92);
    });
    fireEvent.mouseDown(screen.getByRole("tab", { name: t.periods.all }), { button: 0 });
    await waitFor(() => {
      expect(span()).toBe(366); // не больше года (docs/08 §1)
    });
  });

  it("пустой отчёт: подсказки вместо графиков, без процентов", async () => {
    mockMe("student");
    mockReport(
      report({
        homework_weekly: [],
        homework_last_percent: null,
        on_time: { on_time_count: 0, total_count: 0, percent: null },
        mock_exams: [],
      }),
    );
    renderRoutes(routes, ["/app/reports"]);
    expect(await screen.findByText(t.homework.none)).toBeInTheDocument();
    expect(screen.getByText(t.mock.none)).toBeInTheDocument();
    expect(screen.getByText(t.onTime.none)).toBeInTheDocument();
    expect(screen.queryByRole("img", { name: t.homework.title })).toBeNull();
  });

  it("ошибка загрузки: сообщение и «Повторить»", async () => {
    mockMe("student");
    server.use(
      http.get("*/api/v1/student/reports", () =>
        HttpResponse.json(
          { error: { code: "invalid_period", message: "x", details: {} } },
          { status: 422 },
        ),
      ),
    );
    renderRoutes(routes, ["/app/reports"]);
    expect(await screen.findByRole("alert")).toHaveTextContent(texts.errors.invalid_period);
  });

  it("в отчёте нет денег и заметок", async () => {
    mockMe("student");
    mockReport(report());
    renderRoutes(routes, ["/app/reports"]);
    await screen.findByText(t.homework.last(85));
    expect(document.body.textContent).not.toMatch(/₽|цена|заметк/i);
  });
});

describe("Вкладка «Пробники и прогресс» карточки ученика", () => {
  const card = {
    user_id: 5,
    display_name: "Аня Иванова",
    timezone: "Europe/Moscow",
    is_active: true,
    bot_blocked: false,
    telegram_linked: true,
    teacher_id: 1,
    school_class: 9,
    video_url: null,
    board_url: null,
    teacher_notes: null,
    subjects: [],
  };

  it("открывается по вкладке: запрос отчёта ученика и кнопка ввода пробника", async () => {
    mockMe("manager");
    server.use(http.get("*/api/v1/admin/students/5", () => HttpResponse.json(card)));
    mockReport(report(), "*/api/v1/admin/students/5/report");
    renderRoutes(routes, ["/admin/students/5"]);
    fireEvent.mouseDown(
      await screen.findByRole("tab", { name: texts.admin.students.tabs.progress }),
      { button: 0 },
    );
    expect(await screen.findByText(t.homework.last(85))).toBeInTheDocument();
    expect(screen.getByRole("button", { name: texts.admin.exams.newResult })).toBeInTheDocument();
    expect(lastQuery?.get("from")).not.toBeNull();
  });

  it("архивному ученику ввод пробника недоступен", async () => {
    mockMe("manager");
    server.use(
      http.get("*/api/v1/admin/students/5", () => HttpResponse.json({ ...card, is_active: false })),
    );
    mockReport(report(), "*/api/v1/admin/students/5/report");
    renderRoutes(routes, ["/admin/students/5"]);
    fireEvent.mouseDown(
      await screen.findByRole("tab", { name: texts.admin.students.tabs.progress }),
      { button: 0 },
    );
    await screen.findByText(t.homework.last(85));
    expect(screen.queryByRole("button", { name: texts.admin.exams.newResult })).toBeNull();
  });
});
