import { fireEvent, screen, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { texts } from "@/lib/texts";
import { routes } from "@/router";
import { mockMe } from "@/test/mockMe";
import { renderRoutes } from "@/test/renderRoutes";
import { server } from "@/test/server";

const t = texts.admin.homework;

const NOW = new Date("2026-10-14T12:00:00Z");

const STUDENTS = {
  items: [11, 12].map((id) => ({
    user_id: id,
    display_name: id === 11 ? "Аня Иванова" : "Борис Орлов",
    school_class: 9,
    is_active: true,
    bot_blocked: false,
    telegram_linked: true,
    invite_pending: false,
    subjects: [],
  })),
  total: 2,
  limit: 200,
  offset: 0,
};

const row = (patch: Record<string, unknown> = {}) => ({
  assignment_id: 7,
  homework_id: 3,
  title: "Задачи 1-5",
  kind: "regular",
  student_id: 11,
  student_name: "Аня Иванова",
  status: "submitted",
  due_at: "2026-10-20T17:00:00Z",
  is_overdue: false,
  extensions_count: 0,
  submitted_at: "2026-10-14T10:00:00Z",
  score: null,
  max_score: 13,
  ...patch,
});

const file = (id: number, role = "student_solution", type = "image/jpeg") => ({
  id,
  assignment_id: 7,
  role,
  original_name: `work-${String(id)}.jpg`,
  content_type: type,
  size_bytes: 1000,
  created_at: "2026-10-14T10:00:00Z",
});

const detail = (patch: Record<string, unknown> = {}) => ({
  ...row(),
  description: null,
  original_due_at: "2026-10-20T17:00:00Z",
  on_time: true,
  submission_type: "files",
  student_comment: "Сделала всё",
  teacher_comment: null,
  graded_after_expiry: false,
  score_percent: null,
  materials: [],
  files: [file(1), file(2)],
  extensions: [],
  ...patch,
});

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"], now: NOW });
  mockMe("manager");
  server.use(
    http.get("*/api/v1/admin/students", () => HttpResponse.json(STUDENTS)),
    http.get("*/api/v1/files/:id/url", ({ params }) =>
      HttpResponse.json({ url: `https://files.test/${String(params["id"])}.jpg`, expires_in: 600 }),
    ),
  );
});
afterEach(() => {
  vi.useRealTimers();
});

describe("ДЗ: список и очередь", () => {
  it("очередь проверки показывает сданные работы со ссылкой на проверку", async () => {
    server.use(
      http.get("*/api/v1/admin/assignments/review-queue", () =>
        HttpResponse.json({ items: [row()], total: 1, limit: 50, offset: 0 }),
      ),
    );
    renderRoutes(routes, ["/admin/homework"]);
    const link = await screen.findByRole("link", { name: /Аня Иванова/ });
    expect(link).toHaveAttribute("href", "/admin/assignments/7");
    expect(screen.getByText(/Сдано 14 октября 2026/)).toBeInTheDocument();
  });

  it("пустая очередь и список заданий «сдали N из M»", async () => {
    server.use(
      http.get("*/api/v1/admin/assignments/review-queue", () =>
        HttpResponse.json({ items: [], total: 0, limit: 50, offset: 0 }),
      ),
      http.get("*/api/v1/admin/homework", () =>
        HttpResponse.json({
          items: [
            {
              id: 3,
              kind: "regular",
              title: "Задачи 1-5",
              subject_code: "informatics",
              max_score: 5,
              created_at: "2026-10-14T10:00:00Z",
              assigned_count: 4,
              submitted_count: 2,
            },
          ],
          total: 1,
          limit: 50,
          offset: 0,
        }),
      ),
    );
    renderRoutes(routes, ["/admin/homework"]);
    expect(await screen.findByText(t.queueEmpty)).toBeInTheDocument();
    fireEvent.mouseDown(screen.getByRole("tab", { name: t.tabHomework }), { button: 0 });
    fireEvent.click(screen.getByRole("tab", { name: t.tabHomework }));
    expect(await screen.findByText("сдали 2 из 4")).toBeInTheDocument();
  });

  it("ошибка загрузки очереди с повтором", async () => {
    server.use(
      http.get("*/api/v1/admin/assignments/review-queue", () =>
        HttpResponse.json(
          { error: { code: "internal_error", message: "x", details: {} } },
          { status: 500 },
        ),
      ),
    );
    renderRoutes(routes, ["/admin/homework"]);
    expect(await screen.findByRole("alert")).toHaveTextContent(texts.errors.internal_error);
  });
});

describe("ДЗ: создание", () => {
  it("отправляет срок в UTC и выбранных учеников; «Выбрать всех» отмечает всех", async () => {
    server.use(
      http.get("*/api/v1/admin/assignments/review-queue", () =>
        HttpResponse.json({ items: [], total: 0, limit: 50, offset: 0 }),
      ),
    );
    let body: Record<string, unknown> = {};
    server.use(
      http.post("*/api/v1/admin/homework", async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: 3 }, { status: 201 });
      }),
    );
    renderRoutes(routes, ["/admin/homework"]);
    fireEvent.click(await screen.findByRole("button", { name: t.newHomework }));
    fireEvent.change(await screen.findByLabelText(t.form.name), {
      target: { value: "Задачи 1-5" },
    });
    fireEvent.click(await screen.findByRole("button", { name: t.form.selectAll }));
    await waitFor(() => {
      expect(screen.getByRole("checkbox", { name: "Борис Орлов" })).toBeChecked();
    });
    fireEvent.click(screen.getByRole("button", { name: t.form.submit }));
    await waitFor(() => {
      expect(body["student_ids"]).toEqual([11, 12]);
    });
    expect(body).toMatchObject({
      kind: "regular",
      title: "Задачи 1-5",
      max_score: 5,
      due_mode: "next_lesson",
      due_at: "2026-10-21T17:00:00.000Z",
    });
  });

  it("без названия и учеников форма не отправляется", async () => {
    server.use(
      http.get("*/api/v1/admin/assignments/review-queue", () =>
        HttpResponse.json({ items: [], total: 0, limit: 50, offset: 0 }),
      ),
    );
    let posted = false;
    server.use(
      http.post("*/api/v1/admin/homework", () => {
        posted = true;
        return HttpResponse.json({}, { status: 201 });
      }),
    );
    renderRoutes(routes, ["/admin/homework"]);
    fireEvent.click(await screen.findByRole("button", { name: t.newHomework }));
    fireEvent.click(await screen.findByRole("button", { name: t.form.submit }));
    expect(await screen.findByText(t.form.errors.nameRequired)).toBeInTheDocument();
    expect(screen.getByText(t.form.errors.studentsRequired)).toBeInTheDocument();
    expect(posted).toBe(false);
  });
});

describe("ДЗ: экран проверки", () => {
  it("показывает файлы ученика, перелистывание и подсказку «из 13»", async () => {
    server.use(http.get("*/api/v1/admin/assignments/7", () => HttpResponse.json(detail())));
    renderRoutes(routes, ["/admin/assignments/7"]);
    expect(await screen.findByAltText("work-1.jpg")).toHaveAttribute(
      "src",
      "https://files.test/1.jpg",
    );
    expect(screen.getByText("1 из 2")).toBeInTheDocument();
    expect(screen.getByText("Сделала всё")).toBeInTheDocument();
    expect(screen.getByText(t.scoreOf(13))).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: t.review.next }));
    expect(await screen.findByAltText("work-2.jpg")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: t.review.next })).toBeDisabled();
    const zoomIn = screen.getByRole("button", { name: t.review.zoomIn });
    fireEvent.click(zoomIn);
    expect(screen.getByAltText("work-2.jpg")).toHaveStyle({ width: "150%" });
  });

  it("оценка: балл выше максимума не отправляется, верный уходит числом", async () => {
    server.use(http.get("*/api/v1/admin/assignments/7", () => HttpResponse.json(detail())));
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post("*/api/v1/admin/assignments/7/grade", async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ assignment_id: 7, status: "graded" });
      }),
    );
    renderRoutes(routes, ["/admin/assignments/7"]);
    const score = await screen.findByLabelText(t.review.score);
    fireEvent.change(score, { target: { value: "14" } });
    fireEvent.click(screen.getByRole("button", { name: t.review.save }));
    expect(await screen.findByText(t.review.errors.scoreRange(13))).toBeInTheDocument();
    expect(body).toBeNull();
    fireEvent.change(score, { target: { value: "11" } });
    fireEvent.change(screen.getByLabelText(t.review.comment), { target: { value: "Хорошо" } });
    fireEvent.click(screen.getByRole("button", { name: t.review.save }));
    await waitFor(() => {
      expect(body).toEqual({ score: 11, comment: "Хорошо" });
    });
  });

  it("возврат на доработку требует комментарий и отправляет его", async () => {
    server.use(http.get("*/api/v1/admin/assignments/7", () => HttpResponse.json(detail())));
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post("*/api/v1/admin/assignments/7/return", async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ assignment_id: 7, status: "needs_revision" });
      }),
    );
    renderRoutes(routes, ["/admin/assignments/7"]);
    fireEvent.click(await screen.findByRole("button", { name: t.review.returnButton }));
    fireEvent.click(await screen.findByRole("button", { name: t.review.returnSubmit }));
    expect(await screen.findByText(t.review.errors.commentRequired)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(t.review.returnComment), {
      target: { value: "Исправь №3" },
    });
    fireEvent.click(screen.getByRole("button", { name: t.review.returnSubmit }));
    await waitFor(() => {
      expect(body).toEqual({ comment: "Исправь №3", new_due_at: null });
    });
  });

  it("перенос срока: показывает «Осталось 1 из 2»", async () => {
    server.use(
      http.get("*/api/v1/admin/assignments/7", () =>
        HttpResponse.json(detail({ status: "assigned", extensions_count: 1, files: [] })),
      ),
    );
    renderRoutes(routes, ["/admin/assignments/7"]);
    expect(await screen.findByText(t.review.extendLeft(1, 2))).toBeInTheDocument();
    expect(screen.getByRole("button", { name: t.review.extend })).toBeEnabled();
  });

  it("после двух переносов кнопка неактивна с пояснением", async () => {
    server.use(
      http.get("*/api/v1/admin/assignments/7", () =>
        HttpResponse.json(detail({ status: "assigned", extensions_count: 2, files: [] })),
      ),
    );
    renderRoutes(routes, ["/admin/assignments/7"]);
    expect(await screen.findByText(t.review.extendNone)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: t.review.extend })).toBeDisabled();
  });

  it("нет следующего занятия: появляется ручной срок и уходит due_at в UTC", async () => {
    server.use(
      http.get("*/api/v1/admin/assignments/7", () =>
        HttpResponse.json(detail({ status: "assigned", files: [] })),
      ),
    );
    const bodies: unknown[] = [];
    server.use(
      http.post("*/api/v1/admin/assignments/7/extend", async ({ request }) => {
        const body: unknown = await request.json();
        bodies.push(body);
        if (bodies.length === 1) {
          return HttpResponse.json(
            { error: { code: "no_next_lesson", message: "x", details: {} } },
            { status: 400 },
          );
        }
        return HttpResponse.json({ assignment_id: 7, extensions_left: 1 });
      }),
    );
    renderRoutes(routes, ["/admin/assignments/7"]);
    fireEvent.click(await screen.findByRole("button", { name: t.review.extend }));
    expect(await screen.findByText(t.review.extendManual)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(t.form.date), { target: { value: "2026-10-25" } });
    fireEvent.click(screen.getByRole("button", { name: t.review.extendManualSubmit }));
    await waitFor(() => {
      expect(bodies).toHaveLength(2);
    });
    expect(bodies[0]).toEqual({});
    expect(bodies[1]).toEqual({ due_at: "2026-10-25T17:00:00.000Z" });
  });

  it("оценённая работа показывает итог и журнал переносов", async () => {
    server.use(
      http.get("*/api/v1/admin/assignments/7", () =>
        HttpResponse.json(
          detail({
            status: "graded",
            score: 11,
            score_percent: 85,
            extensions: [
              {
                old_due_at: "2026-10-18T17:00:00Z",
                new_due_at: "2026-10-20T17:00:00Z",
                created_by: 1,
                created_at: "2026-10-17T10:00:00Z",
              },
            ],
          }),
        ),
      ),
    );
    renderRoutes(routes, ["/admin/assignments/7"]);
    expect(await screen.findByText("Оценка: 11 из 13 (85%)")).toBeInTheDocument();
    expect(screen.getByText(t.review.extensionsLog)).toBeInTheDocument();
  });

  it("ошибка загрузки выдачи с повтором", async () => {
    server.use(
      http.get("*/api/v1/admin/assignments/7", () =>
        HttpResponse.json(
          { error: { code: "assignment_not_found", message: "x", details: {} } },
          { status: 404 },
        ),
      ),
    );
    renderRoutes(routes, ["/admin/assignments/7"]);
    expect(await screen.findByRole("alert")).toHaveTextContent(texts.errors.assignment_not_found);
  });
});
