import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { routes } from "@/router";
import { texts } from "@/lib/texts";
import { mockMe } from "@/test/mockMe";
import { chooseSubject } from "@/test/chooseSubject";
import { renderRoutes } from "@/test/renderRoutes";
import { server } from "@/test/server";
import { setViewport } from "@/test/viewport";

const t = texts.admin.schedule;

// Среда, 14 октября 2026, 15:00 по Москве.
const NOW = new Date("2026-10-14T12:00:00Z");

const lesson = (id: number, start: string, patch: Record<string, unknown> = {}) => ({
  id,
  teacher_id: 1,
  subject_code: "informatics",
  start_at: start,
  end_at: new Date(new Date(start).getTime() + 3_600_000).toISOString(),
  status: "scheduled",
  is_detached: false,
  video_url_override: null,
  board_url_override: null,
  topic: null,
  teacher_note: null,
  completed_at: null,
  cancelled_at: null,
  cancel_reason: null,
  participants: [
    { student_id: 11, display_name: "Аня Иванова", attendance: "pending" },
    { student_id: 12, display_name: "Борис Орлов", attendance: "pending" },
  ],
  ...patch,
});

const STUDENTS = {
  items: [
    {
      user_id: 11,
      display_name: "Аня Иванова",
      school_class: 9,
      is_active: true,
      bot_blocked: false,
      telegram_linked: true,
      invite_pending: false,
      subjects: [],
    },
    {
      user_id: 12,
      display_name: "Борис Орлов",
      school_class: 11,
      is_active: true,
      bot_blocked: false,
      telegram_linked: true,
      invite_pending: false,
      subjects: [],
    },
  ],
  total: 2,
  limit: 200,
  offset: 0,
};

let lastQuery: URLSearchParams | null = null;

function mockSchedule(items: unknown[]) {
  server.use(
    http.get("*/api/v1/admin/lessons", ({ request }) => {
      lastQuery = new URL(request.url).searchParams;
      return HttpResponse.json({ items, total: items.length, limit: 200, offset: 0 });
    }),
    http.get("*/api/v1/admin/students", () => HttpResponse.json(STUDENTS)),
  );
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"], now: NOW });
  lastQuery = null;
});
afterEach(() => {
  vi.useRealTimers();
});

describe("Расписание: просмотр", () => {
  it("мобильный вид: неделя запрашивается по границам суток пользователя, виден выбранный день", async () => {
    mockMe("manager");
    mockSchedule([lesson(1, "2026-10-14T14:00:00Z"), lesson(2, "2026-10-15T14:00:00Z")]);
    renderRoutes(routes, ["/admin/schedule"]);
    expect(await screen.findByText("17:00–18:00")).toBeInTheDocument();
    // понедельник 12 октября 00:00 МСК = 11 октября 21:00 UTC; неделя — до следующего понедельника
    expect(lastQuery?.get("from")).toBe("2026-10-11T21:00:00.000Z");
    expect(lastQuery?.get("to")).toBe("2026-10-18T21:00:00.000Z");
    // урок четверга скрыт, пока не выбран его день
    expect(screen.getAllByText("17:00–18:00")).toHaveLength(1);
    fireEvent.click(screen.getByRole("tab", { name: /чт, 15 окт/ }));
    expect(await screen.findByText("17:00–18:00")).toBeInTheDocument();
  });

  it("десктоп: неделя колонками по дням", async () => {
    setViewport(1280);
    mockMe("manager");
    mockSchedule([lesson(1, "2026-10-14T14:00:00Z"), lesson(2, "2026-10-15T08:00:00Z")]);
    renderRoutes(routes, ["/admin/schedule"]);
    const wednesday = await screen.findByRole("region", { name: /ср, 14 окт/ });
    expect(within(wednesday).getByText("17:00–18:00")).toBeInTheDocument();
    const thursday = screen.getByRole("region", { name: /чт, 15 окт/ });
    expect(within(thursday).getByText("11:00–12:00")).toBeInTheDocument();
    expect(screen.getAllByRole("region")).toHaveLength(7);
  });

  it("урок около полуночи попадает в день по поясу пользователя", async () => {
    mockMe("manager");
    // 21:30 UTC 14 октября = 00:30 15 октября по Москве
    mockSchedule([lesson(1, "2026-10-14T21:30:00Z")]);
    renderRoutes(routes, ["/admin/schedule"]);
    expect(await screen.findByText(t.noLessonsDay)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: /чт, 15 окт/ }));
    expect(await screen.findByText("00:30–01:30")).toBeInTheDocument();
  });

  it("пусто и ошибка с повтором", async () => {
    mockMe("manager");
    server.use(
      http.get("*/api/v1/admin/lessons", () =>
        HttpResponse.json(
          { error: { code: "internal_error", message: "x", details: {} } },
          { status: 500 },
        ),
      ),
      http.get("*/api/v1/admin/students", () => HttpResponse.json(STUDENTS)),
    );
    renderRoutes(routes, ["/admin/schedule"]);
    expect(await screen.findByRole("alert")).toHaveTextContent(texts.errors.internal_error);
    mockSchedule([]);
    fireEvent.click(screen.getByRole("button", { name: texts.login.retry }));
    expect(await screen.findByText(t.noLessonsDay)).toBeInTheDocument();
    expect(screen.getByText(t.emptyHint)).toBeInTheDocument();
  });

  it("фильтры уходят в запрос", async () => {
    mockMe("manager");
    mockSchedule([]);
    renderRoutes(routes, ["/admin/schedule"]);
    await screen.findByText(t.noLessonsDay);
    fireEvent.change(screen.getByLabelText(t.filterStatus), { target: { value: "cancelled" } });
    await waitFor(() => {
      expect(lastQuery?.get("status")).toBe("cancelled");
    });
    await screen.findByRole("option", { name: "Борис Орлов" });
    fireEvent.change(screen.getByLabelText(t.filterStudent), { target: { value: "12" } });
    await waitFor(() => {
      expect(lastQuery?.get("student_id")).toBe("12");
    });
  });
});

describe("Расписание: создание урока", () => {
  it("отправляет время в UTC и закрывает форму", async () => {
    mockMe("manager");
    mockSchedule([]);
    let body: Record<string, unknown> = {};
    server.use(
      http.post("*/api/v1/admin/lessons", async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(lesson(5, "2026-10-14T14:00:00Z"), { status: 201 });
      }),
    );
    renderRoutes(routes, ["/admin/schedule"]);
    fireEvent.click(await screen.findByRole("button", { name: t.newLesson }));
    await chooseSubject();
    fireEvent.click(await screen.findByRole("checkbox", { name: "Аня Иванова" }));
    fireEvent.click(screen.getByRole("button", { name: t.form.submitCreate }));
    await waitFor(() => {
      expect(body["start_at"]).toBe("2026-10-14T14:00:00.000Z");
    });
    expect(body).toMatchObject({
      subject_code: "informatics",
      student_ids: [11],
      end_at: "2026-10-14T15:00:00.000Z",
    });
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).toBeNull();
    });
  });

  it("без участников форма не отправляется", async () => {
    mockMe("manager");
    mockSchedule([]);
    let posted = false;
    server.use(
      http.post("*/api/v1/admin/lessons", () => {
        posted = true;
        return HttpResponse.json({}, { status: 201 });
      }),
    );
    renderRoutes(routes, ["/admin/schedule"]);
    fireEvent.click(await screen.findByRole("button", { name: t.newLesson }));
    await screen.findByRole("checkbox", { name: "Аня Иванова" });
    fireEvent.click(screen.getByRole("button", { name: t.form.submitCreate }));
    expect(await screen.findByText(t.form.errors.participantsRequired)).toBeInTheDocument();
    expect(posted).toBe(false);
  });

  it("пересечение показывает «В это время уже есть урок»", async () => {
    mockMe("manager");
    mockSchedule([]);
    server.use(
      http.post("*/api/v1/admin/lessons", () =>
        HttpResponse.json(
          { error: { code: "lesson_overlap", message: "x", details: {} } },
          { status: 409 },
        ),
      ),
    );
    renderRoutes(routes, ["/admin/schedule"]);
    fireEvent.click(await screen.findByRole("button", { name: t.newLesson }));
    await chooseSubject();
    fireEvent.click(await screen.findByRole("checkbox", { name: "Аня Иванова" }));
    fireEvent.click(screen.getByRole("button", { name: t.form.submitCreate }));
    const alert = await screen.findByText(/В это время уже есть урок/);
    expect(alert).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});

describe("Расписание: шаблон", () => {
  it("предпросмотр ближайших дат и отправка шаблона", async () => {
    mockMe("manager");
    mockSchedule([]);
    let body: Record<string, unknown> = {};
    server.use(
      http.post("*/api/v1/admin/schedule-templates", async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: 1 }, { status: 201 });
      }),
    );
    renderRoutes(routes, ["/admin/schedule"]);
    fireEvent.click(await screen.findByRole("button", { name: t.newTemplate }));
    // по умолчанию вторник; сегодня среда 14 октября → 20, 27 октября, 3 и 10 ноября
    const preview = await screen.findByRole("list", { name: t.template.preview });
    expect(
      within(preview)
        .getAllByRole("listitem")
        .map((li) => li.textContent),
    ).toEqual(["вт, 20 окт", "вт, 27 окт", "вт, 3 нояб", "вт, 10 нояб"]);
    await chooseSubject();
    fireEvent.click(await screen.findByRole("checkbox", { name: "Борис Орлов" }));
    fireEvent.click(screen.getByRole("button", { name: t.template.submit }));
    await waitFor(() => {
      expect(body["weekday"]).toBe(2);
    });
    expect(body).toMatchObject({
      student_ids: [12],
      start_local_time: "17:00:00",
      timezone: "Europe/Moscow",
      starts_on: "2026-10-14",
      ends_on: null,
    });
  });

  it("период с датой окончания ограничивает предпросмотр", async () => {
    mockMe("manager");
    mockSchedule([]);
    renderRoutes(routes, ["/admin/schedule"]);
    fireEvent.click(await screen.findByRole("button", { name: t.newTemplate }));
    fireEvent.change(await screen.findByLabelText(t.template.endsOn), {
      target: { value: "2026-10-27" },
    });
    const preview = await screen.findByRole("list", { name: t.template.preview });
    expect(within(preview).getAllByRole("listitem")).toHaveLength(2);
  });
});

describe("Расписание: действия над уроком", () => {
  async function openLesson() {
    mockMe("manager");
    mockSchedule([lesson(7, "2026-10-14T14:00:00Z")]);
    renderRoutes(routes, ["/admin/schedule"]);
    fireEvent.click(await screen.findByRole("button", { name: /17:00–18:00/ }));
    return screen.findByRole("dialog");
  }

  it("отметка проведения: по умолчанию «Был» и «Засчитать»", async () => {
    let body: Record<string, unknown> = {};
    server.use(
      http.post("*/api/v1/admin/lessons/7/complete", async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(lesson(7, "2026-10-14T14:00:00Z", { status: "completed" }));
      }),
    );
    await openLesson();
    fireEvent.click(screen.getByRole("button", { name: t.detail.actions.complete }));
    const anya = await screen.findByRole("checkbox", { name: /Засчитать занятие: Аня/ });
    const boris = screen.getByRole("checkbox", { name: /Засчитать занятие: Борис/ });
    expect(anya).toBeChecked();
    expect(boris).toBeChecked();
    // «Не пришёл» снимает галочку, её можно включить вручную
    const radios = screen.getAllByRole("radio", { name: t.complete.noShow });
    fireEvent.click(radios[1] as HTMLElement);
    expect(boris).not.toBeChecked();
    expect(anya).toBeChecked();
    fireEvent.click(screen.getByRole("button", { name: t.complete.submit }));
    await waitFor(() => {
      expect(body["marks"]).toEqual([
        { student_id: 11, attendance: "attended", is_billable: true },
        { student_id: 12, attendance: "no_show", is_billable: false },
      ]);
    });
  });

  it("менеджер не видит цену в отметке проведения", async () => {
    await openLesson();
    fireEvent.click(screen.getByRole("button", { name: t.detail.actions.complete }));
    await screen.findByRole("checkbox", { name: /Засчитать занятие: Аня/ });
    expect(screen.getByRole("dialog").textContent).not.toMatch(/₽|цена/i);
  });

  it("отмена: причина и «Засчитать отмену»", async () => {
    let body: Record<string, unknown> = {};
    server.use(
      http.post("*/api/v1/admin/lessons/7/cancel", async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(lesson(7, "2026-10-14T14:00:00Z", { status: "cancelled" }));
      }),
    );
    await openLesson();
    fireEvent.click(screen.getByRole("button", { name: t.detail.actions.cancel }));
    fireEvent.change(await screen.findByLabelText(t.cancel.reason), {
      target: { value: "Болезнь" },
    });
    fireEvent.click(screen.getByRole("checkbox", { name: /Засчитать отмену: Борис/ }));
    fireEvent.click(screen.getByRole("button", { name: t.cancel.submit }));
    await waitFor(() => {
      expect(body).toEqual({ reason: "Болезнь", billable_student_ids: [12] });
    });
  });

  it("перенос: форма предзаполнена, время уходит в UTC", async () => {
    let body: Record<string, unknown> = {};
    server.use(
      http.post("*/api/v1/admin/lessons/7/reschedule", async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(lesson(7, "2026-10-15T07:30:00Z"));
      }),
    );
    await openLesson();
    fireEvent.click(screen.getByRole("button", { name: t.detail.actions.reschedule }));
    const date = await screen.findByLabelText(t.form.date);
    expect(date).toHaveValue("2026-10-14");
    expect(screen.getByLabelText(t.form.time)).toHaveValue("17:00");
    fireEvent.change(date, { target: { value: "2026-10-15" } });
    fireEvent.change(screen.getByLabelText(t.form.time), { target: { value: "10:30" } });
    fireEvent.click(screen.getByRole("button", { name: t.reschedule.submit }));
    await waitFor(() => {
      expect(body).toEqual({
        start_at: "2026-10-15T07:30:00.000Z",
        end_at: "2026-10-15T08:30:00.000Z",
      });
    });
  });

  it("у проведённого урока действий нет", async () => {
    mockMe("manager");
    mockSchedule([lesson(7, "2026-10-14T14:00:00Z", { status: "completed" })]);
    renderRoutes(routes, ["/admin/schedule"]);
    fireEvent.click(await screen.findByRole("button", { name: /17:00–18:00/ }));
    await screen.findByRole("dialog");
    expect(screen.queryByRole("button", { name: t.detail.actions.complete })).toBeNull();
  });
});
