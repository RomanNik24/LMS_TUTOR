/**
 * Состояния экранов (T8.05, docs/07 §6.16): загрузка, ошибка с «Повторить», нет сети, пусто, данные
 * — для пяти самых важных экранов.
 */
import { fireEvent, screen, within } from "@testing-library/react";
import { HttpResponse, delay, http } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { texts } from "@/lib/texts";
import { routes } from "@/router";
import { mockMe } from "@/test/mockMe";
import { renderRoutes } from "@/test/renderRoutes";
import { server } from "@/test/server";
import type { Role } from "@/features/auth/api";

const NOW = new Date("2026-10-14T10:00:00Z");

const EMPTY_BLOCK = { total: 0, items: [] };
const EMPTY_PAGE = { items: [], total: 0, limit: 20, offset: 0 };

type Screen = {
  name: string;
  role: Role;
  route: string;
  /** Путь запроса, который отдаёт данные экрана. */
  url: string;
  /** Тело ответа «данных нет» и признак пустого состояния. */
  empty: unknown;
  emptyText: string | RegExp;
};

const SCREENS: Screen[] = [
  {
    name: "Расписание ученика",
    role: "student",
    route: "/app/schedule",
    url: "*/api/v1/student/lessons",
    empty: [],
    emptyText: texts.empty.studentSchedule.text,
  },
  {
    name: "ДЗ ученика",
    role: "student",
    route: "/app/homework",
    url: "*/api/v1/student/homework",
    empty: EMPTY_PAGE,
    emptyText: texts.student.homework.empty.active,
  },
  {
    name: "Отчёты ученика",
    role: "student",
    route: "/app/reports",
    url: "*/api/v1/student/reports",
    empty: {
      student_id: 1,
      timezone: "Europe/Moscow",
      homework_weekly: [],
      homework_last_percent: null,
      on_time: { on_time_count: 0, total_count: 0, percent: null },
      mock_exams: [],
      attendance: { attended: 0, no_show: 0, cancelled: 0, pending: 0 },
    },
    emptyText: texts.student.reports.homework.none,
  },
  {
    name: "Дашборд «Сегодня»",
    role: "manager",
    route: "/admin/today",
    url: "*/api/v1/admin/dashboard/today",
    empty: {
      date: "2026-10-14",
      timezone: "Europe/Moscow",
      lessons: EMPTY_BLOCK,
      review_queue: EMPTY_BLOCK,
      unsubmitted: EMPTY_BLOCK,
      unmarked_lessons: EMPTY_BLOCK,
      deadlines: EMPTY_BLOCK,
    },
    emptyText: texts.admin.dashboard.allGood,
  },
  {
    name: "Очередь проверки",
    role: "manager",
    route: "/admin/homework",
    url: "*/api/v1/admin/assignments/review-queue",
    empty: EMPTY_PAGE,
    emptyText: texts.admin.homework.queueEmpty,
  },
];

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"], now: NOW });
});
afterEach(() => {
  vi.useRealTimers();
});

describe.each(SCREENS)("$name", (screenCase) => {
  const respond = (body: unknown) => {
    server.use(http.get(screenCase.url, () => HttpResponse.json(body as Record<string, unknown>)));
  };

  it("загрузка: скелетон со статусом «Загрузка»", async () => {
    mockMe(screenCase.role);
    server.use(
      http.get(screenCase.url, async () => {
        await delay("infinite");
        return HttpResponse.json({});
      }),
    );
    renderRoutes(routes, [screenCase.route]);

    const status = await screen.findAllByRole("status", { name: texts.common.loading });
    expect(status.length).toBeGreaterThan(0);
  });

  it("пусто: понятная подсказка", async () => {
    mockMe(screenCase.role);
    respond(screenCase.empty);
    renderRoutes(routes, [screenCase.route]);

    expect((await screen.findAllByText(screenCase.emptyText)).length).toBeGreaterThan(0);
  });

  it("ошибка сервера: текст по коду и «Повторить» возвращает данные", async () => {
    mockMe(screenCase.role);
    let failing = true;
    server.use(
      http.get(screenCase.url, () =>
        failing
          ? HttpResponse.json(
              { error: { code: "internal_error", message: "x", details: {} } },
              { status: 500 },
            )
          : HttpResponse.json(screenCase.empty as Record<string, unknown>),
      ),
    );
    renderRoutes(routes, [screenCase.route]);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(texts.errors.internal_error);
    failing = false;
    fireEvent.click(within(alert).getByRole("button", { name: texts.login.retry }));

    expect((await screen.findAllByText(screenCase.emptyText)).length).toBeGreaterThan(0);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("нет сети: сообщение о связи и «Повторить»", async () => {
    mockMe(screenCase.role);
    server.use(http.get(screenCase.url, () => HttpResponse.error()));
    renderRoutes(routes, [screenCase.route]);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(texts.errors.network);
    expect(within(alert).getByRole("button", { name: texts.login.retry })).toBeInTheDocument();
  });
});

describe("Плашка «Нет соединения»", () => {
  afterEach(() => {
    Object.defineProperty(window.navigator, "onLine", { configurable: true, value: true });
  });

  it("появляется при потере сети и пропадает при возврате", async () => {
    mockMe("student");
    server.use(http.get("*/api/v1/student/lessons", () => HttpResponse.json([])));
    renderRoutes(routes, ["/app/schedule"]);
    await screen.findByText(texts.empty.studentSchedule.text);
    expect(screen.queryByText(texts.messages.offlineBanner)).toBeNull();

    Object.defineProperty(window.navigator, "onLine", { configurable: true, value: false });
    fireEvent(window, new Event("offline"));
    expect(await screen.findByText(texts.messages.offlineBanner)).toBeInTheDocument();

    Object.defineProperty(window.navigator, "onLine", { configurable: true, value: true });
    fireEvent(window, new Event("online"));
    expect(screen.queryByText(texts.messages.offlineBanner)).toBeNull();
  });
});
