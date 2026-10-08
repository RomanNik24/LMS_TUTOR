import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { texts } from "@/lib/texts";
import { routes } from "@/router";
import { mockMe } from "@/test/mockMe";
import { renderRoutes } from "@/test/renderRoutes";
import { server } from "@/test/server";

import { periodRange } from "./api";

const t = texts.admin.finance;

const NOW = new Date("2026-10-14T10:00:00Z"); // среда, Москва UTC+3
const NO_CUSTOM = { from: "", to: "" };

const row = (key: string, label: string, earned: number, expected: number) => ({
  key,
  label,
  earned,
  earned_lessons: 2,
  expected,
  planned_lessons: 1,
});

const report = (groupBy: string, rows: unknown[], earned = 5200, expected = 5500) => ({
  period_start: "2026-09-30T21:00:00Z",
  period_end: "2026-10-31T21:00:00Z",
  group_by: groupBy,
  timezone: "Europe/Moscow",
  earned_total: earned,
  expected_total: expected,
  rows,
});

function mockFinance(queries: URLSearchParams[] = []) {
  server.use(
    http.get("*/api/v1/admin/finance/earnings", ({ request }) => {
      const params = new URL(request.url).searchParams;
      queries.push(params);
      const group = params.get("group_by") ?? "month";
      if (group === "week") {
        return HttpResponse.json(report("week", [row("2026-10-05", "2026-10-05", 3500, 0)]));
      }
      if (group === "subject") {
        return HttpResponse.json(
          report("subject", [row("informatics", "Информатика", 5200, 5500)]),
        );
      }
      return HttpResponse.json(
        report("student", [row("11", "Аня Иванова", 2700, 4000), row("12", "Борис", 2500, 1500)]),
      );
    }),
    http.get("*/api/v1/admin/stats/cancellations", () =>
      HttpResponse.json({
        period_start: "2026-09-30T21:00:00Z",
        period_end: "2026-10-31T21:00:00Z",
        cancelled_lessons: 3,
        cancelled_participations: 4,
        by_student: [],
      }),
    ),
  );
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"], now: NOW });
});
afterEach(() => {
  vi.useRealTimers();
});

describe("periodRange", () => {
  it("неделя — с понедельника до следующего понедельника в поясе владельца", () => {
    expect(periodRange("week", NO_CUSTOM, "Europe/Moscow")).toEqual({
      from: "2026-10-11T21:00:00.000Z",
      to: "2026-10-18T21:00:00.000Z",
    });
  });

  it("месяц — календарный месяц", () => {
    expect(periodRange("month", NO_CUSTOM, "Europe/Moscow")).toEqual({
      from: "2026-09-30T21:00:00.000Z",
      to: "2026-10-31T21:00:00.000Z",
    });
  });

  it("свой период включает последний день и не длиннее года", () => {
    expect(
      periodRange("custom", { from: "2026-10-01", to: "2026-10-03" }, "Europe/Moscow")?.to,
    ).toBe("2026-10-03T21:00:00.000Z");
    expect(periodRange("custom", { from: "2026-10-05", to: "2026-10-01" }, "UTC")).toBeNull();
    expect(periodRange("custom", { from: "2025-01-01", to: "2026-10-01" }, "UTC")).toBeNull();
    expect(periodRange("custom", NO_CUSTOM, "UTC")).toBeNull();
  });
});

describe("Финансы", () => {
  it("владелец: карточки, таблица по ученикам, график по неделям; срез «по предметам»", async () => {
    mockMe("owner");
    const queries: URLSearchParams[] = [];
    mockFinance(queries);
    renderRoutes(routes, ["/admin/finance"]);

    expect(await screen.findByText(/5\s200\s₽/)).toBeInTheDocument();
    expect(screen.getByText(/5\s500\s₽/)).toBeInTheDocument();
    expect(screen.getByText(t.cancellationsDetail(3, 4))).toBeInTheDocument();
    expect(screen.getByRole("row", { name: /Аня Иванова/ })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: t.chartTitle })).toBeInTheDocument();
    expect(screen.getByText(/Неделя с пн, 5 окт: 3\s500\s₽/)).toBeInTheDocument();
    expect(queries.some((query) => query.get("group_by") === "week")).toBe(true);

    fireEvent.mouseDown(screen.getByRole("tab", { name: t.slices.subject }));
    fireEvent.click(screen.getByRole("tab", { name: t.slices.subject }));
    expect(await screen.findByRole("row", { name: /Информатика/ })).toBeInTheDocument();
  });

  it("«Экспорт CSV» скачивает файл за выбранный период", async () => {
    mockMe("owner");
    mockFinance();
    let exported: URLSearchParams | null = null;
    server.use(
      http.get("*/api/v1/admin/finance/export.csv", ({ request }) => {
        exported = new URL(request.url).searchParams;
        return new HttpResponse("Дата,Ученик\r\n", { headers: { "Content-Type": "text/csv" } });
      }),
    );
    const createUrl = vi.fn(() => "blob:csv");
    const revoke = vi.fn();
    vi.stubGlobal(
      "URL",
      Object.assign(URL, { createObjectURL: createUrl, revokeObjectURL: revoke }),
    );
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => undefined);
    renderRoutes(routes, ["/admin/finance"]);

    fireEvent.click(await screen.findByRole("button", { name: t.export }));

    await waitFor(() => {
      expect(click).toHaveBeenCalledTimes(1);
    });
    expect(exported).not.toBeNull();
    expect(createUrl).toHaveBeenCalledTimes(1);
    expect(revoke).toHaveBeenCalledWith("blob:csv");
    click.mockRestore();
    vi.unstubAllGlobals();
  });

  it("неверный свой период: сообщение, экспорт недоступен", async () => {
    mockMe("owner");
    mockFinance();
    renderRoutes(routes, ["/admin/finance"]);

    fireEvent.mouseDown(await screen.findByRole("tab", { name: t.periods.custom }));
    fireEvent.click(screen.getByRole("tab", { name: t.periods.custom }));
    fireEvent.change(await screen.findByLabelText(t.from), { target: { value: "2026-10-20" } });
    fireEvent.change(screen.getByLabelText(t.to), { target: { value: "2026-10-01" } });

    expect(await screen.findByText(t.invalidPeriod)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: t.export })).toBeDisabled();
  });

  it("менеджер не попадает на экран финансов", async () => {
    mockMe("manager");
    mockFinance();
    const { router } = renderRoutes(routes, ["/admin/finance"]);

    await waitFor(() => {
      expect(router.state.location.pathname).not.toBe("/admin/finance");
    });
    expect(screen.queryByText(t.earned)).toBeNull();
    expect(document.body.textContent).not.toMatch(/₽/);
  });
});

describe("Карточка ученика: вкладка «Финансы»", () => {
  const owner = {
    user_id: 11,
    display_name: "Аня Иванова",
    school_class: 9,
    is_active: true,
    bot_blocked: false,
    telegram_linked: true,
    timezone: "Europe/Moscow",
    video_url: null,
    board_url: null,
    teacher_notes: null,
    subjects: [],
    lesson_price: 2000,
  };

  it("владелец видит заработок и ожидаемое по ученику", async () => {
    mockMe("owner");
    mockFinance();
    server.use(http.get("*/api/v1/admin/students/11", () => HttpResponse.json(owner)));
    renderRoutes(routes, ["/admin/students/11"]);

    const tab = await screen.findByRole("tab", { name: texts.admin.students.tabs.finance });
    fireEvent.mouseDown(tab);
    fireEvent.click(tab);

    const panel = await screen.findByText(t.studentTab.title);
    expect(panel).toBeInTheDocument();
    expect(await screen.findByText(/2\s700\s₽/)).toBeInTheDocument();
    expect(screen.getByText(/4\s000\s₽/)).toBeInTheDocument();
  });

  it("у менеджера вкладки «Финансы» нет", async () => {
    mockMe("manager");
    const manager = Object.fromEntries(
      Object.entries(owner).filter(([key]) => key !== "lesson_price"),
    );
    server.use(http.get("*/api/v1/admin/students/11", () => HttpResponse.json(manager)));
    renderRoutes(routes, ["/admin/students/11"]);

    await screen.findByRole("tab", { name: texts.admin.students.tabs.overview });
    expect(screen.queryByRole("tab", { name: texts.admin.students.tabs.finance })).toBeNull();
    expect(within(document.body).queryByText(/₽/)).toBeNull();
  });
});
