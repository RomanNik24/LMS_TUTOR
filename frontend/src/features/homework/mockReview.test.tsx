import { fireEvent, screen, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { texts } from "@/lib/texts";
import { routes } from "@/router";
import { mockMe } from "@/test/mockMe";
import { renderRoutes } from "@/test/renderRoutes";
import { server } from "@/test/server";

const t = texts.admin.homework.review;

const NOW = new Date("2026-10-14T12:00:00Z");

const detail = (patch: Record<string, unknown> = {}) => ({
  assignment_id: 7,
  homework_id: 3,
  title: "Пробник ОГЭ",
  kind: "mock_exam",
  exam_type_id: 2,
  student_id: 11,
  student_name: "Аня Иванова",
  status: "submitted",
  due_at: "2026-10-20T17:00:00Z",
  is_overdue: false,
  extensions_count: 0,
  submitted_at: "2026-10-14T10:00:00Z",
  score: null,
  max_score: 31,
  description: null,
  original_due_at: "2026-10-20T17:00:00Z",
  on_time: true,
  submission_type: "self_reported",
  student_comment: null,
  teacher_comment: null,
  graded_after_expiry: false,
  score_percent: null,
  materials: [],
  files: [],
  extensions: [],
  ...patch,
});

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"], now: NOW });
  mockMe("manager");
});
afterEach(() => {
  vi.useRealTimers();
});

describe("Проверка пробника: конвертация", () => {
  it("ОГЭ математика: поле геометрии, мгновенная конвертация и баллы уходят в оценку", async () => {
    server.use(http.get("*/api/v1/admin/assignments/7", () => HttpResponse.json(detail())));
    const previews: Record<string, unknown>[] = [];
    server.use(
      http.post("*/api/v1/admin/mock-exams/convert", async ({ request }) => {
        const body = (await request.json()) as Record<string, unknown>;
        previews.push(body);
        return HttpResponse.json({
          converted_value: body["geometry_score"] === 1 ? 2 : 5,
          scale_year: 2026,
          scale_applicable: true,
          warning: body["geometry_score"] === null ? "geometry_missing" : null,
        });
      }),
    );
    let graded: Record<string, unknown> | null = null;
    server.use(
      http.post("*/api/v1/admin/assignments/7/grade", async ({ request }) => {
        graded = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ assignment_id: 7, status: "graded" });
      }),
    );
    renderRoutes(routes, ["/admin/assignments/7"]);
    const score = await screen.findByLabelText(t.score);
    fireEvent.change(score, { target: { value: "22" } });
    expect(await screen.findByText(texts.exams.gradeOf(22, 5))).toBeInTheDocument();
    expect(screen.getByText(texts.exams.geometryMissing)).toBeInTheDocument();
    expect(previews.at(-1)).toMatchObject({
      exam_type_id: 2,
      primary_score: 22,
      max_primary: 31,
      geometry_score: null,
    });

    fireEvent.change(screen.getByLabelText(t.geometry), { target: { value: "1" } });
    expect(await screen.findByText(texts.exams.gradeOf(22, 2))).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: t.save }));
    await waitFor(() => {
      expect(graded).toEqual({ score: 22, comment: null, geometry_score: 1 });
    });
  });

  it("балл выше максимума: конвертация не запрашивается, ошибка поля", async () => {
    server.use(http.get("*/api/v1/admin/assignments/7", () => HttpResponse.json(detail())));
    let asked = false;
    server.use(
      http.post("*/api/v1/admin/mock-exams/convert", () => {
        asked = true;
        return HttpResponse.json({});
      }),
    );
    renderRoutes(routes, ["/admin/assignments/7"]);
    fireEvent.change(await screen.findByLabelText(t.score), { target: { value: "32" } });
    fireEvent.click(screen.getByRole("button", { name: t.save }));
    expect(await screen.findByText(t.errors.scoreRange(31))).toBeInTheDocument();
    expect(asked).toBe(false);
  });

  it("обычное ДЗ: нет ни геометрии, ни конвертации", async () => {
    server.use(
      http.get("*/api/v1/admin/assignments/7", () =>
        HttpResponse.json(detail({ kind: "regular", exam_type_id: null, max_score: 13 })),
      ),
    );
    renderRoutes(routes, ["/admin/assignments/7"]);
    fireEvent.change(await screen.findByLabelText(t.score), { target: { value: "5" } });
    expect(screen.queryByLabelText(t.geometry)).toBeNull();
    expect(screen.queryByText(t.mockConversion)).toBeNull();
  });

  it("пробник ЕГЭ информатики: «тестовый», поля геометрии нет", async () => {
    server.use(
      http.get("*/api/v1/admin/assignments/7", () =>
        HttpResponse.json(detail({ exam_type_id: 3, max_score: 29, title: "Пробник ЕГЭ" })),
      ),
      http.post("*/api/v1/admin/mock-exams/convert", () =>
        HttpResponse.json({
          converted_value: 78,
          scale_year: 2026,
          scale_applicable: true,
          warning: null,
        }),
      ),
    );
    renderRoutes(routes, ["/admin/assignments/7"]);
    fireEvent.change(await screen.findByLabelText(t.score), { target: { value: "20" } });
    expect(await screen.findByText(texts.exams.testOf(20, 78))).toBeInTheDocument();
    expect(screen.queryByLabelText(t.geometry)).toBeNull();
  });
});
