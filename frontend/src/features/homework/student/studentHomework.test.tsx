import { fireEvent, screen, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { texts } from "@/lib/texts";
import { routes } from "@/router";
import { mockMe } from "@/test/mockMe";
import { renderRoutes } from "@/test/renderRoutes";
import { server } from "@/test/server";

import { validateFile } from "./FileUploader";

const t = texts.student.homework;
const NOW = new Date("2026-10-14T12:00:00Z");

const item = (patch: Record<string, unknown> = {}) => ({
  assignment_id: 7,
  homework_id: 3,
  title: "Задачи 1-5",
  kind: "regular",
  subject_code: "informatics",
  status: "assigned",
  due_at: "2026-10-20T17:00:00Z",
  is_overdue: false,
  extensions_left: 2,
  max_score: 13,
  score: null,
  score_percent: null,
  submitted_at: null,
  ...patch,
});

const file = (id: number, role = "student_solution") => ({
  id,
  assignment_id: 7,
  role,
  original_name: `${role}-${String(id)}.jpg`,
  content_type: "image/jpeg",
  size_bytes: 1000,
  created_at: "2026-10-14T10:00:00Z",
});

const detail = (patch: Record<string, unknown> = {}) => ({
  ...item(),
  description: "Решить задачи",
  original_due_at: "2026-10-20T17:00:00Z",
  on_time: null,
  submission_type: null,
  student_comment: null,
  teacher_comment: null,
  materials: [],
  files: [],
  ...patch,
});

function mockDetail(patch: Record<string, unknown> = {}) {
  server.use(http.get("*/api/v1/student/homework/7", () => HttpResponse.json(detail(patch))));
}

function renderCard() {
  return renderRoutes(routes, ["/app/homework/7"]);
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"], now: NOW });
  mockMe("student");
  server.use(
    http.get("*/api/v1/files/:id/url", () =>
      HttpResponse.json({ url: "https://files.test/x.jpg", expires_in: 600 }),
    ),
  );
});
afterEach(() => {
  vi.useRealTimers();
});

describe("ДЗ ученика: список", () => {
  it("активные: просроченные с красным бейджем, запрос с фильтром status", async () => {
    let status: string | null = null;
    server.use(
      http.get("*/api/v1/student/homework", ({ request }) => {
        status = new URL(request.url).searchParams.get("status");
        return HttpResponse.json({
          items: [item({ is_overdue: true, title: "Старое" }), item({ assignment_id: 8 })],
          total: 2,
          limit: 50,
          offset: 0,
        });
      }),
    );
    renderRoutes(routes, ["/app/homework"]);
    expect(await screen.findByText("Старое")).toBeInTheDocument();
    expect(status).toBe("active");
    expect(screen.getByText(texts.status["homework.overdue"])).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Старое/ })).toHaveAttribute("href", "/app/homework/7");
  });

  it("пусто: «Все ДЗ сделаны…»; проверенные показывают чип результата", async () => {
    server.use(
      http.get("*/api/v1/student/homework", ({ request }) => {
        const status = new URL(request.url).searchParams.get("status");
        const items =
          status === "graded" ? [item({ status: "graded", score: 11, score_percent: 85 })] : [];
        return HttpResponse.json({ items, total: items.length, limit: 50, offset: 0 });
      }),
    );
    renderRoutes(routes, ["/app/homework"]);
    expect(await screen.findByText(t.empty.active)).toBeInTheDocument();
    fireEvent.mouseDown(screen.getByRole("tab", { name: t.tabGraded }), { button: 0 });
    fireEvent.click(screen.getByRole("tab", { name: t.tabGraded }));
    expect(await screen.findByText("11 из 13 · 85%")).toBeInTheDocument();
  });

  it("ошибка загрузки показывает сообщение", async () => {
    server.use(
      http.get("*/api/v1/student/homework", () =>
        HttpResponse.json(
          { error: { code: "internal_error", message: "x", details: {} } },
          { status: 500 },
        ),
      ),
    );
    renderRoutes(routes, ["/app/homework"]);
    expect(await screen.findByRole("alert")).toHaveTextContent(texts.errors.internal_error);
  });
});

describe("ДЗ ученика: карточка по статусам", () => {
  it("assigned: «Сдать» неактивна без файлов, «Сделал» отправляет комментарий", async () => {
    mockDetail();
    let body: unknown = null;
    server.use(
      http.post("*/api/v1/student/homework/7/self-report", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ assignment_id: 7, status: "submitted" });
      }),
    );
    renderCard();
    expect(await screen.findByText("Решить задачи")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: t.submit })).toBeDisabled();
    expect(screen.getByText(t.submitHint)).toBeInTheDocument();
    expect(screen.getByText(t.extensionsLeft(2))).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(t.comment), { target: { value: " готово " } });
    fireEvent.click(screen.getByRole("button", { name: t.selfReport }));
    await waitFor(() => {
      expect(body).toEqual({ student_comment: "готово" });
    });
  });

  it("assigned с файлом: «Сдать» активна и отправляет submit", async () => {
    mockDetail({ files: [file(1)] });
    let called = false;
    server.use(
      http.post("*/api/v1/student/homework/7/submit", () => {
        called = true;
        return HttpResponse.json({ assignment_id: 7, status: "submitted" });
      }),
    );
    renderCard();
    const button = await screen.findByRole("button", { name: t.submit });
    expect(button).toBeEnabled();
    fireEvent.click(button);
    await waitFor(() => {
      expect(called).toBe(true);
    });
  });

  it("просрочено, но не сгорело: сдача доступна, бейдж красный", async () => {
    mockDetail({ is_overdue: true });
    renderCard();
    expect(await screen.findByText(texts.status["homework.overdue"])).toBeInTheDocument();
    expect(screen.getByRole("button", { name: t.selfReport })).toBeEnabled();
  });

  it("needs_revision: плашка с комментарием преподавателя и возможность сдать", async () => {
    mockDetail({ status: "needs_revision", teacher_comment: "Исправь №3", files: [file(1)] });
    renderCard();
    expect(await screen.findByText("Исправь №3")).toBeInTheDocument();
    expect(screen.getByText(t.revision)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: t.submit })).toBeEnabled();
  });

  it("submitted: «на проверке», файлы без удаления и без кнопки сдачи", async () => {
    mockDetail({ status: "submitted", on_time: true, files: [file(1)] });
    renderCard();
    expect(await screen.findByText(t.submitted)).toBeInTheDocument();
    expect(screen.getByText(t.submittedOnTime)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: t.submit })).toBeNull();
    expect(screen.queryByRole("button", { name: /Удалить файл/ })).toBeNull();
  });

  it("graded: чип «11 из 13 · 85%», комментарий и файлы проверки", async () => {
    mockDetail({
      status: "graded",
      score: 11,
      score_percent: 85,
      teacher_comment: "Хорошо",
      files: [file(1), file(2, "teacher_review")],
    });
    renderCard();
    expect((await screen.findAllByText("11 из 13 · 85%")).length).toBeGreaterThan(0);
    expect(screen.getByText("Хорошо")).toBeInTheDocument();
    expect(await screen.findByAltText("teacher_review-2.jpg")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: t.submit })).toBeNull();
  });

  it("expired: сдача заблокирована и объяснена", async () => {
    mockDetail({ status: "expired" });
    renderCard();
    expect(await screen.findByText(t.expired)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: t.submit })).toBeNull();
    expect(screen.queryByRole("button", { name: t.selfReport })).toBeNull();
  });

  it("чужая или несуществующая выдача: ошибка 404", async () => {
    server.use(
      http.get("*/api/v1/student/homework/7", () =>
        HttpResponse.json(
          { error: { code: "assignment_not_found", message: "x", details: {} } },
          { status: 404 },
        ),
      ),
    );
    renderCard();
    expect(await screen.findByRole("alert")).toHaveTextContent(texts.errors.assignment_not_found);
  });
});

describe("ДЗ ученика: загрузчик", () => {
  it("validateFile: тип, размер и лимит 10 файлов", () => {
    const make = (name: string, size = 100, type = "") =>
      new File([new Uint8Array(size)], name, { type });
    expect(validateFile(make("a.jpg"), 0)).toBeNull();
    expect(validateFile(make("IMG_1.HEIC"), 0)).toBeNull();
    expect(validateFile(make("a.pdf", 100, "application/pdf"), 9)).toBeNull();
    expect(validateFile(make("a.exe"), 0)).toBe(t.uploader.wrongType);
    expect(validateFile(make("a.jpg", 10 * 1024 * 1024 + 1), 0)).toBe(t.uploader.tooLarge);
    expect(validateFile(make("a.jpg"), 10)).toBe(t.uploader.limitReached);
  });

  it("загрузка отправляет multipart и обновляет карточку; ошибка 415 показывается", async () => {
    let files: File[] = [];
    let calls = 0;
    mockDetail();
    server.use(
      http.post("*/api/v1/student/homework/7/files", async ({ request }) => {
        const form = await request.formData();
        const sent = form.get("file");
        // File из jsdom и из MSW — разные классы, instanceof не подходит
        files = sent !== null && typeof sent !== "string" ? [sent] : [];
        calls += 1;
        if (calls === 1) {
          return HttpResponse.json(
            { error: { code: "unsupported_file_type", message: "x", details: {} } },
            { status: 415 },
          );
        }
        return HttpResponse.json(file(5), { status: 201 });
      }),
    );
    renderCard();
    const input = await screen.findByTestId("solution-input");
    fireEvent.change(input, {
      target: { files: [new File(["x"], "bad.jpg", { type: "image/jpeg" })] },
    });
    expect(await screen.findByText(texts.errors.unsupported_file_type)).toBeInTheDocument();
    mockDetail({ files: [file(5)] });
    fireEvent.change(input, {
      target: { files: [new File(["x"], "work.jpg", { type: "image/jpeg" })] },
    });
    await waitFor(() => {
      expect(calls).toBe(2);
      // jsdom теряет имя файла в multipart, поэтому проверяем сам факт части «file»
      expect(files).toHaveLength(1);
    });
    expect(await screen.findByText("student_solution-5.jpg")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: t.submit })).toBeEnabled();
  });

  it("слишком большой файл отклоняется до отправки", async () => {
    mockDetail();
    renderCard();
    const input = await screen.findByTestId("solution-input");
    const big = new File([new Uint8Array(10 * 1024 * 1024 + 1)], "big.jpg", { type: "image/jpeg" });
    fireEvent.change(input, { target: { files: [big] } });
    expect(await screen.findByText(t.uploader.tooLarge)).toBeInTheDocument();
  });

  it("удаление файла отправляет DELETE", async () => {
    mockDetail({ files: [file(5)] });
    let deleted = false;
    server.use(
      http.delete("*/api/v1/student/homework/7/files/5", () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderCard();
    fireEvent.click(await screen.findByRole("button", { name: /Удалить файл/ }));
    await waitFor(() => {
      expect(deleted).toBe(true);
    });
  });
});
