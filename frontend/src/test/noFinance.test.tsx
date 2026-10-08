/**
 * Деньги видит только владелец (docs/09 §3, docs/06 B7): на экранах ученика и менеджера нет цен,
 * сумм заработка и финансовых разделов, даже если сервер по ошибке прислал бы лишние поля.
 */
import { screen, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { texts } from "@/lib/texts";
import { routes } from "@/router";
import { mockMe } from "@/test/mockMe";
import { renderRoutes } from "@/test/renderRoutes";
import { server } from "@/test/server";

const NOW = new Date("2026-10-14T10:00:00Z");
const FINANCE = /₽|заработан|ожидается|цена занятия|выручк|финанс/i;
const EMPTY = { total: 0, items: [] };

const lesson = {
  id: 1,
  subject_code: "informatics",
  start_at: "2026-10-14T14:00:00Z",
  end_at: "2026-10-14T15:00:00Z",
  status: "scheduled",
  topic: "Графы",
  video_url: "https://telemost.yandex.ru/j/1",
  board_url: null,
  participants_count: 1,
  homework: [],
};

const assignment = {
  assignment_id: 7,
  homework_id: 3,
  title: "Задачи 1-5",
  kind: "regular",
  subject_code: "informatics",
  status: "graded",
  due_at: "2026-10-12T17:00:00Z",
  is_overdue: false,
  extensions_left: 2,
  max_score: 13,
  score: 11,
  score_percent: 85,
  submitted_at: "2026-10-11T10:00:00Z",
};

const managerCard = {
  user_id: 11,
  display_name: "Аня Иванова",
  school_class: 9,
  is_active: true,
  bot_blocked: false,
  telegram_linked: true,
  timezone: "Europe/Moscow",
  video_url: null,
  board_url: null,
  teacher_notes: "Заметка",
  subjects: ["informatics"],
};

const dashboard = {
  date: "2026-10-14",
  timezone: "Europe/Moscow",
  lessons: EMPTY,
  review_queue: EMPTY,
  unsubmitted: EMPTY,
  unmarked_lessons: EMPTY,
  deadlines: EMPTY,
};

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"], now: NOW });
});
afterEach(() => {
  vi.useRealTimers();
});

describe("ученик: нет денег", () => {
  it.each([
    ["/app/schedule", () => screen.findByText("Графы")],
    ["/app/homework", () => screen.findByText("Задачи 1-5")],
  ])("%s", async (route, ready) => {
    mockMe("student");
    server.use(
      http.get("*/api/v1/student/lessons", () => HttpResponse.json([lesson])),
      http.get("*/api/v1/student/homework", () =>
        HttpResponse.json({ items: [assignment], total: 1, limit: 20, offset: 0 }),
      ),
    );
    renderRoutes(routes, [route]);
    await ready();

    expect(document.body.textContent).not.toMatch(FINANCE);
  });

  it("ученика не пускают на экраны персонала и финансов", async () => {
    mockMe("student");
    const { router } = renderRoutes(routes, ["/admin/finance"]);

    await waitFor(() => {
      expect(router.state.location.pathname).not.toBe("/admin/finance");
    });
    expect(document.body.textContent).not.toMatch(FINANCE);
  });
});

describe("менеджер: нет денег", () => {
  it("дашборд, карточка ученика и меню «Ещё» без финансов", async () => {
    mockMe("manager");
    server.use(
      http.get("*/api/v1/admin/dashboard/today", () => HttpResponse.json(dashboard)),
      http.get("*/api/v1/admin/students/11", () => HttpResponse.json(managerCard)),
    );

    const today = renderRoutes(routes, ["/admin/today"]);
    await screen.findAllByText(texts.admin.dashboard.allGood);
    expect(document.body.textContent).not.toMatch(FINANCE);
    today.unmount();

    const card = renderRoutes(routes, ["/admin/students/11"]);
    await screen.findByText("Аня Иванова");
    expect(screen.queryByRole("tab", { name: texts.admin.students.tabs.finance })).toBeNull();
    expect(document.body.textContent).not.toMatch(FINANCE);
    card.unmount();

    renderRoutes(routes, ["/admin/more"]);
    await screen.findByText(texts.nav.admin.exams);
    expect(screen.queryByText(texts.nav.admin.finance)).toBeNull();
  });

  it("прямой адрес /admin/finance уводит с экрана", async () => {
    mockMe("manager");
    const { router } = renderRoutes(routes, ["/admin/finance"]);

    await waitFor(() => {
      expect(router.state.location.pathname).not.toBe("/admin/finance");
    });
  });
});
