import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { texts } from "@/lib/texts";
import { routes } from "@/router";
import { mockMe } from "@/test/mockMe";
import { renderRoutes } from "@/test/renderRoutes";
import { server } from "@/test/server";

const t = texts.admin.exams;

const NOW = new Date("2026-05-20T12:00:00Z");

const STUDENTS = {
  items: [11].map((id) => ({
    user_id: id,
    display_name: "Аня Иванова",
    school_class: 9,
    is_active: true,
    bot_blocked: false,
    telegram_linked: true,
    invite_pending: false,
    subjects: [],
  })),
  total: 1,
  limit: 200,
  offset: 0,
};

const result = (id: number, patch: Record<string, unknown> = {}) => ({
  id,
  student_id: 11,
  student_name: "Аня Иванова",
  exam_type_id: 3,
  exam_type_code: "ege_informatics",
  exam_type_name: "ЕГЭ — Информатика",
  exam_date: "2026-05-18",
  primary_score: 20,
  max_primary: 29,
  geometry_score: null,
  converted_value: 78,
  scale_year: 2026,
  scale_applicable: true,
  warning: null,
  assignment_id: null,
  comment: null,
  ...patch,
});

function mockList(items: unknown[]) {
  server.use(
    http.get("*/api/v1/admin/mock-exams", () =>
      HttpResponse.json({ items, total: items.length, limit: 20, offset: 0 }),
    ),
  );
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"], now: NOW });
  mockMe("manager");
  server.use(http.get("*/api/v1/admin/students", () => HttpResponse.json(STUDENTS)));
});
afterEach(() => {
  vi.useRealTimers();
});

describe("Пробники: список", () => {
  it("показывает оценку, тестовый балл и «Шкала не применима»; результаты из ДЗ не удаляются", async () => {
    mockList([
      result(1),
      result(2, {
        exam_type_id: 1,
        exam_type_name: "ОГЭ — Информатика",
        primary_score: 17,
        max_primary: 21,
        converted_value: 5,
        assignment_id: 40,
      }),
      result(3, { max_primary: 27, converted_value: null, scale_applicable: false }),
    ]);
    renderRoutes(routes, ["/admin/exams"]);
    expect(await screen.findByText(texts.exams.testLabel(78))).toBeInTheDocument();
    expect(screen.getByText(texts.exams.gradeLabel(5))).toBeInTheDocument();
    expect(screen.getByText(texts.exams.notApplicable)).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: t.delete })).toHaveLength(2);
    expect(screen.getByText(t.fromHomework)).toBeInTheDocument();
  });

  it("пусто: подсказка; ошибка: «Повторить»", async () => {
    mockList([]);
    renderRoutes(routes, ["/admin/exams"]);
    expect(await screen.findByText(t.empty)).toBeInTheDocument();
  });

  it("фильтры отправляют student_id и exam_type_id", async () => {
    let query: URLSearchParams | null = null;
    server.use(
      http.get("*/api/v1/admin/mock-exams", ({ request }) => {
        query = new URL(request.url).searchParams;
        return HttpResponse.json({ items: [], total: 0, limit: 20, offset: 0 });
      }),
    );
    renderRoutes(routes, ["/admin/exams"]);
    await screen.findByText(t.empty);
    fireEvent.change(await screen.findByLabelText(t.filterExam), { target: { value: "3" } });
    await waitFor(() => {
      expect(query?.get("exam_type_id")).toBe("3");
    });
    await screen.findByRole("option", { name: "Аня Иванова" });
    fireEvent.change(screen.getByLabelText(t.filterStudent), { target: { value: "11" } });
    await waitFor(() => {
      expect(query?.get("student_id")).toBe("11");
    });
  });

  it("удаление ручного результата — после подтверждения", async () => {
    mockList([result(1)]);
    let deleted = false;
    server.use(
      http.delete("*/api/v1/admin/mock-exams/1", () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderRoutes(routes, ["/admin/exams"]);
    fireEvent.click(await screen.findByRole("button", { name: t.delete }));
    expect(deleted).toBe(false);
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: t.deleteConfirm }));
    await waitFor(() => {
      expect(deleted).toBe(true);
    });
  });
});

describe("Пробники: форма ввода", () => {
  const f = t.form;

  async function openForm() {
    mockList([]);
    renderRoutes(routes, ["/admin/exams"]);
    await screen.findByText(t.empty);
    fireEvent.click(screen.getByRole("button", { name: t.newResult }));
    const dialog = await screen.findByRole("dialog");
    await within(dialog).findByRole("option", { name: "Аня Иванова" });
    await within(dialog).findByRole("option", { name: "ЕГЭ — Информатика" });
    return within(dialog);
  }

  type Conversion = {
    converted_value: number | null;
    scale_year: number | null;
    scale_applicable: boolean;
    warning: string | null;
  };

  function mockConvert(handler: (body: Record<string, unknown>) => Conversion) {
    const bodies: Record<string, unknown>[] = [];
    server.use(
      http.post("*/api/v1/admin/mock-exams/convert", async ({ request }) => {
        const body = (await request.json()) as Record<string, unknown>;
        bodies.push(body);
        return HttpResponse.json(handler(body));
      }),
    );
    return bodies;
  }

  it("конвертация видна сразу: максимум подставлен официальный, ЕГЭ — «тестовый»", async () => {
    const bodies = mockConvert(() => ({
      converted_value: 78,
      scale_year: 2026,
      scale_applicable: true,
      warning: null,
    }));
    const form = await openForm();
    fireEvent.change(form.getByLabelText(f.exam), { target: { value: "3" } });
    expect(form.getByLabelText(f.max)).toHaveValue("29");
    fireEvent.change(form.getByLabelText(f.primary), { target: { value: "20" } });
    expect(await screen.findByText(texts.exams.testOf(20, 78))).toBeInTheDocument();
    expect(bodies.at(-1)).toEqual({
      exam_type_id: 3,
      exam_date: "2026-05-20",
      primary_score: 20,
      max_primary: 29,
      geometry_score: null,
    });
  });

  it("нестандартный максимум (27): «Шкала не применима»", async () => {
    mockConvert((body) => ({
      converted_value: null,
      scale_year: null,
      scale_applicable: body["max_primary"] === 29,
      warning: null,
    }));
    const form = await openForm();
    fireEvent.change(form.getByLabelText(f.exam), { target: { value: "3" } });
    fireEvent.change(form.getByLabelText(f.max), { target: { value: "27" } });
    fireEvent.change(form.getByLabelText(f.primary), { target: { value: "20" } });
    expect(await screen.findByText(texts.exams.notApplicable)).toBeInTheDocument();
  });

  it("ОГЭ математика: поле геометрии и предупреждение, если оно не заполнено", async () => {
    const bodies = mockConvert((body) => ({
      converted_value: body["geometry_score"] === 1 ? 2 : 5,
      scale_year: 2026,
      scale_applicable: true,
      warning: body["geometry_score"] === null ? "geometry_missing" : null,
    }));
    const form = await openForm();
    expect(form.queryByLabelText(f.geometry)).toBeNull();
    fireEvent.change(form.getByLabelText(f.exam), { target: { value: "2" } });
    fireEvent.change(form.getByLabelText(f.primary), { target: { value: "22" } });
    expect(await screen.findByText(texts.exams.geometryMissing)).toBeInTheDocument();
    expect(screen.getByText(texts.exams.gradeOf(22, 5))).toBeInTheDocument();
    fireEvent.change(form.getByLabelText(f.geometry), { target: { value: "1" } });
    expect(await screen.findByText(texts.exams.gradeOf(22, 2))).toBeInTheDocument();
    expect(screen.queryByText(texts.exams.geometryMissing)).toBeNull();
    expect(bodies.at(-1)?.["geometry_score"]).toBe(1);
  });

  it("балл выше максимума: ошибка поля, запрос не уходит", async () => {
    let posted = false;
    server.use(
      http.post("*/api/v1/admin/mock-exams", () => {
        posted = true;
        return HttpResponse.json({}, { status: 201 });
      }),
    );
    const form = await openForm();
    fireEvent.change(form.getByLabelText(f.student), { target: { value: "11" } });
    fireEvent.change(form.getByLabelText(f.exam), { target: { value: "3" } });
    fireEvent.change(form.getByLabelText(f.primary), { target: { value: "30" } });
    fireEvent.click(form.getByRole("button", { name: f.submit }));
    expect(await screen.findByText(f.errors.scoreAboveMax)).toBeInTheDocument();
    expect(posted).toBe(false);
  });

  it("сохранение отправляет ученика, экзамен, дату и баллы и закрывает форму", async () => {
    mockConvert(() => ({
      converted_value: 78,
      scale_year: 2026,
      scale_applicable: true,
      warning: null,
    }));
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post("*/api/v1/admin/mock-exams", async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(result(9), { status: 201 });
      }),
    );
    const form = await openForm();
    fireEvent.change(form.getByLabelText(f.student), { target: { value: "11" } });
    fireEvent.change(form.getByLabelText(f.exam), { target: { value: "3" } });
    fireEvent.change(form.getByLabelText(f.primary), { target: { value: "20" } });
    fireEvent.change(form.getByLabelText(f.comment), { target: { value: "Вариант 3" } });
    fireEvent.click(form.getByRole("button", { name: f.submit }));
    await waitFor(() => {
      expect(body).toEqual({
        student_id: 11,
        exam_type_id: 3,
        exam_date: "2026-05-20",
        primary_score: 20,
        max_primary: 29,
        geometry_score: null,
        comment: "Вариант 3",
      });
    });
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).toBeNull();
    });
  });

  it("ошибка сервера показывается понятным текстом", async () => {
    mockConvert(() => ({
      converted_value: 78,
      scale_year: 2026,
      scale_applicable: true,
      warning: null,
    }));
    server.use(
      http.post("*/api/v1/admin/mock-exams", () =>
        HttpResponse.json(
          { error: { code: "student_not_found", message: "x", details: {} } },
          { status: 404 },
        ),
      ),
    );
    const form = await openForm();
    fireEvent.change(form.getByLabelText(f.student), { target: { value: "11" } });
    fireEvent.change(form.getByLabelText(f.exam), { target: { value: "3" } });
    fireEvent.change(form.getByLabelText(f.primary), { target: { value: "20" } });
    fireEvent.click(form.getByRole("button", { name: f.submit }));
    expect(await screen.findByText(texts.errors.student_not_found)).toBeInTheDocument();
  });
});
