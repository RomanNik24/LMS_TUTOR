import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { routes } from "@/router";
import { texts } from "@/lib/texts";
import { mockMe } from "@/test/mockMe";
import { renderRoutes } from "@/test/renderRoutes";
import { server } from "@/test/server";

const t = texts.student.schedule;

// Среда, 14 октября 2026, 15:00 по Москве.
const NOW = new Date("2026-10-14T12:00:00Z");

const lesson = (id: number, start: string, patch: Record<string, unknown> = {}) => ({
  id,
  subject_code: "informatics",
  start_at: start,
  end_at: new Date(new Date(start).getTime() + 3_600_000).toISOString(),
  status: "scheduled",
  topic: null,
  video_url: "https://telemost.yandex.ru/j/1",
  board_url: null,
  participants_count: 1,
  homework: [],
  ...patch,
});

let lastQuery: URLSearchParams | null = null;

function mockLessons(items: unknown[]) {
  server.use(
    http.get("*/api/v1/student/lessons", ({ request }) => {
      lastQuery = new URL(request.url).searchParams;
      return HttpResponse.json(items);
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

describe("Расписание ученика: список", () => {
  it("герой: приветствие, ближайший урок, «через …» и кнопка Телемост", async () => {
    mockMe("student", "Аня");
    mockLessons([lesson(1, "2026-10-14T14:15:00Z"), lesson(2, "2026-10-15T14:00:00Z")]);
    renderRoutes(routes, ["/app/schedule"]);
    expect(await screen.findByRole("heading", { name: "Привет, Аня" })).toBeInTheDocument();
    // 14:15 UTC = 17:15 по Москве, до него 2 ч 15 мин
    expect(await screen.findByText(/через 2 ч 15 мин/)).toBeInTheDocument();
    const video = screen.getAllByRole("link", { name: t.card.video })[0];
    expect(video).toHaveAttribute("href", "https://telemost.yandex.ru/j/1");
  });

  it("период запроса считается по суткам ученика (Москва)", async () => {
    mockMe("student");
    mockLessons([]);
    renderRoutes(routes, ["/app/schedule"]);
    await screen.findByText(texts.empty.studentSchedule.text);
    // начало сегодняшнего дня по Москве = 13 октября 21:00 UTC; период 28 дней
    expect(lastQuery?.get("from")).toBe("2026-10-13T21:00:00.000Z");
    expect(lastQuery?.get("to")).toBe("2026-11-10T21:00:00.000Z");
  });

  it("группировка по дням: Сегодня, Завтра, дата", async () => {
    mockMe("student");
    mockLessons([
      lesson(1, "2026-10-14T14:00:00Z"),
      lesson(2, "2026-10-15T14:00:00Z"),
      lesson(3, "2026-10-16T14:00:00Z"),
    ]);
    renderRoutes(routes, ["/app/schedule"]);
    expect(await screen.findByRole("heading", { name: t.today })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: t.tomorrow })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Пятница, 16 октября" })).toBeInTheDocument();
  });

  it("урок после полуночи по Москве попадает в «Завтра», а не «Сегодня»", async () => {
    mockMe("student");
    // 21:30 UTC 14 октября = 00:30 15 октября по Москве
    mockLessons([lesson(1, "2026-10-14T21:30:00Z")]);
    renderRoutes(routes, ["/app/schedule"]);
    expect(await screen.findByRole("heading", { name: t.tomorrow })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: t.today })).toBeNull();
    expect(screen.getAllByText("00:30–01:30").length).toBeGreaterThan(0);
  });

  it("время показывается в поясе ученика, а не Москвы", async () => {
    mockMe("student");
    server.use(
      http.get("*/api/v1/me", () =>
        HttpResponse.json({
          id: 1,
          role: "student",
          display_name: "Аня",
          timezone: "Asia/Yekaterinburg",
        }),
      ),
    );
    mockLessons([lesson(1, "2026-10-14T14:00:00Z")]);
    renderRoutes(routes, ["/app/schedule"]);
    // 14:00 UTC = 19:00 в Екатеринбурге
    expect((await screen.findAllByText("19:00–20:00")).length).toBeGreaterThan(0);
    expect(lastQuery?.get("from")).toBe("2026-10-13T19:00:00.000Z");
  });

  it("отменённый урок остаётся в списке с бейджем и не становится «ближайшим»", async () => {
    mockMe("student");
    mockLessons([lesson(1, "2026-10-14T14:00:00Z", { status: "cancelled" })]);
    renderRoutes(routes, ["/app/schedule"]);
    expect(await screen.findByText(texts.status["lesson.cancelled"])).toBeInTheDocument();
    expect(screen.queryByText(t.nextLesson)).toBeNull();
  });

  it("пусто и ошибка с повтором", async () => {
    mockMe("student");
    server.use(
      http.get("*/api/v1/student/lessons", () =>
        HttpResponse.json(
          { error: { code: "internal_error", message: "x", details: {} } },
          { status: 500 },
        ),
      ),
    );
    renderRoutes(routes, ["/app/schedule"]);
    expect(await screen.findByRole("alert")).toHaveTextContent(texts.errors.internal_error);
    mockLessons([]);
    fireEvent.click(screen.getByRole("button", { name: texts.login.retry }));
    expect(await screen.findByText(texts.empty.studentSchedule.text)).toBeInTheDocument();
  });
});

describe("Расписание ученика: неделя и карточка", () => {
  it("переключатель «Неделя» показывает дни недели с уроками", async () => {
    mockMe("student");
    mockLessons([lesson(1, "2026-10-14T14:00:00Z")]);
    renderRoutes(routes, ["/app/schedule"]);
    await screen.findByRole("heading", { name: t.today });
    fireEvent.mouseDown(screen.getByRole("tab", { name: t.week }));
    fireEvent.click(screen.getByRole("tab", { name: t.week }));
    const wednesday = await screen.findByRole("region", { name: /ср, 14 окт/ });
    expect(within(wednesday).getByText("17:00–18:00")).toBeInTheDocument();
    expect(screen.getAllByRole("region")).toHaveLength(7);
    await waitFor(() => {
      expect(lastQuery?.get("from")).toBe("2026-10-11T21:00:00.000Z");
    });
  });

  it("тап по уроку открывает карточку со ссылками", async () => {
    mockMe("student");
    mockLessons([lesson(5, "2026-10-14T14:00:00Z", { board_url: "https://miro.com/b/1" })]);
    server.use(
      http.get("*/api/v1/student/lessons/5", () =>
        HttpResponse.json(
          lesson(5, "2026-10-14T14:00:00Z", {
            board_url: "https://miro.com/b/1",
            topic: "Графы",
            participants_count: 3,
          }),
        ),
      ),
    );
    renderRoutes(routes, ["/app/schedule"]);
    const cards = await screen.findAllByRole("link", { name: /17:00–18:00/ });
    fireEvent.click(cards[0] as HTMLElement);
    expect(await screen.findByRole("heading", { name: "17:00–18:00" })).toBeInTheDocument();
    expect(screen.getByText("Графы")).toBeInTheDocument();
    expect(screen.getByText(t.card.group(3))).toBeInTheDocument();
    expect(screen.getByRole("link", { name: t.card.board })).toHaveAttribute(
      "href",
      "https://miro.com/b/1",
    );
    expect(screen.getByRole("link", { name: t.card.video })).toBeInTheDocument();
  });

  it("без ссылок показывается подсказка", async () => {
    mockMe("student");
    server.use(
      http.get("*/api/v1/student/lessons/6", () =>
        HttpResponse.json(lesson(6, "2026-10-14T14:00:00Z", { video_url: null })),
      ),
    );
    renderRoutes(routes, ["/app/schedule/6"]);
    expect(await screen.findByText(t.card.noLinks)).toBeInTheDocument();
  });

  it("блок «Домашнее задание»: ссылка на карточку ДЗ, срок и статус; без ДЗ блока нет", async () => {
    mockMe("student");
    server.use(
      http.get("*/api/v1/student/lessons/8", () =>
        HttpResponse.json(
          lesson(8, "2026-10-14T14:00:00Z", {
            homework: [
              {
                assignment_id: 31,
                title: "Графы",
                status: "assigned",
                due_at: "2026-10-16T17:00:00Z",
                is_overdue: true,
              },
            ],
          }),
        ),
      ),
    );
    renderRoutes(routes, ["/app/schedule/8"]);
    expect(await screen.findByRole("heading", { name: t.card.homework })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Графы" })).toHaveAttribute("href", "/app/homework/31");
    // 17:00 UTC = 20:00 по Москве (пояс ученика)
    expect(screen.getByText(/Сдать до .*16 октября 2026.*20:00/)).toBeInTheDocument();
    expect(screen.getByText(texts.status["homework.overdue"])).toBeInTheDocument();
  });

  it("без ДЗ блока «Домашнее задание» нет", async () => {
    mockMe("student");
    server.use(
      http.get("*/api/v1/student/lessons/10", () =>
        HttpResponse.json(lesson(10, "2026-10-14T14:00:00Z")),
      ),
    );
    renderRoutes(routes, ["/app/schedule/10"]);
    await screen.findByText(t.card.video);
    expect(screen.queryByRole("heading", { name: t.card.homework })).toBeNull();
  });

  it("чужой или несуществующий урок: «Урок не найден» и возврат к расписанию", async () => {
    mockMe("student");
    server.use(
      http.get("*/api/v1/student/lessons/9", () =>
        HttpResponse.json(
          { error: { code: "lesson_not_found", message: "x", details: {} } },
          { status: 404 },
        ),
      ),
    );
    renderRoutes(routes, ["/app/schedule/9"]);
    expect(await screen.findByRole("alert")).toHaveTextContent(texts.errors.lesson_not_found);
    expect(screen.getByRole("link", { name: t.card.back })).toHaveAttribute(
      "href",
      "/app/schedule",
    );
  });

  it("в карточке нет цен и заметок", async () => {
    mockMe("student");
    server.use(
      http.get("*/api/v1/student/lessons/7", () =>
        HttpResponse.json(lesson(7, "2026-10-14T14:00:00Z", { topic: "Циклы" })),
      ),
    );
    renderRoutes(routes, ["/app/schedule/7"]);
    await screen.findByText("Циклы");
    expect(document.body.textContent).not.toMatch(/₽|цена|заметк/i);
  });
});
