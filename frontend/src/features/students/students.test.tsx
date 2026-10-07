import { fireEvent, screen, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { routes } from "@/router";
import { texts } from "@/lib/texts";
import { mockMe } from "@/test/mockMe";
import { renderRoutes } from "@/test/renderRoutes";
import { server } from "@/test/server";
import { setViewport } from "@/test/viewport";

const item = {
  user_id: 7,
  display_name: "Аня Иванова",
  school_class: 9,
  is_active: true,
  bot_blocked: true,
  telegram_linked: true,
  invite_pending: false,
  subjects: ["informatics"],
};

const managerCard = {
  user_id: 7,
  display_name: "Аня Иванова",
  timezone: "Europe/Moscow",
  is_active: true,
  bot_blocked: false,
  telegram_linked: false,
  teacher_id: 1,
  school_class: 9,
  video_url: null,
  board_url: null,
  teacher_notes: "Только для персонала",
  subjects: ["informatics"],
};

function mockList(items: unknown[]) {
  server.use(
    http.get("*/api/v1/admin/students", () =>
      HttpResponse.json({ items, total: items.length, limit: 20, offset: 0 }),
    ),
  );
}

describe("Ученики: список", () => {
  it("мобильный вид: карточки с классом, предметом и значком бота", async () => {
    mockMe("manager");
    mockList([item]);
    renderRoutes(routes, ["/admin/students"]);
    expect(await screen.findByText("Аня Иванова")).toBeInTheDocument();
    expect(await screen.findByText(/9 класс · Информатика/)).toBeInTheDocument();
    expect(screen.getByText(texts.status["bot.blocked"])).toBeInTheDocument();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("десктоп: таблица", async () => {
    setViewport(1280);
    mockMe("manager");
    mockList([item]);
    renderRoutes(routes, ["/admin/students"]);
    expect(await screen.findByRole("table")).toBeInTheDocument();
  });

  it("пусто: подсказка и кнопка создания", async () => {
    mockMe("manager");
    mockList([]);
    renderRoutes(routes, ["/admin/students"]);
    expect(await screen.findByText(texts.empty.adminStudents.text)).toBeInTheDocument();
  });

  it("ошибка: «Повторить» перезапрашивает список", async () => {
    mockMe("manager");
    server.use(
      http.get("*/api/v1/admin/students", () =>
        HttpResponse.json(
          { error: { code: "internal_error", message: "x", details: {} } },
          { status: 500 },
        ),
      ),
    );
    renderRoutes(routes, ["/admin/students"]);
    expect(await screen.findByRole("alert")).toHaveTextContent(texts.errors.internal_error);
    mockList([item]);
    fireEvent.click(screen.getByRole("button", { name: texts.login.retry }));
    expect(await screen.findByText("Аня Иванова")).toBeInTheDocument();
  });
});

describe("Ученик: карточка и форма", () => {
  it("менеджер не видит цену и вкладку «Финансы»", async () => {
    mockMe("manager");
    server.use(http.get("*/api/v1/admin/students/7", () => HttpResponse.json(managerCard)));
    renderRoutes(routes, ["/admin/students/7"]);
    expect(await screen.findByText("Только для персонала")).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: texts.admin.students.tabs.finance })).toBeNull();
  });

  it("владелец видит вкладку «Финансы»", async () => {
    mockMe("owner");
    server.use(
      http.get("*/api/v1/admin/students/7", () =>
        HttpResponse.json({ ...managerCard, lesson_price: 1500 }),
      ),
    );
    renderRoutes(routes, ["/admin/students/7"]);
    expect(
      await screen.findByRole("tab", { name: texts.admin.students.tabs.finance }),
    ).toBeInTheDocument();
  });

  it("в форме менеджера нет поля цены, у владельца есть", async () => {
    mockMe("manager");
    renderRoutes(routes, ["/admin/students/new"]);
    await screen.findByLabelText(texts.admin.students.form.name);
    expect(screen.queryByLabelText(texts.admin.students.form.price)).toBeNull();
  });

  it("владелец видит поле цены", async () => {
    mockMe("owner");
    renderRoutes(routes, ["/admin/students/new"]);
    expect(await screen.findByLabelText(texts.admin.students.form.price)).toBeInTheDocument();
  });

  it("невалидные данные не отправляются, ошибки показаны", async () => {
    mockMe("manager");
    let posted = false;
    server.use(
      http.post("*/api/v1/admin/students", () => {
        posted = true;
        return HttpResponse.json(managerCard, { status: 201 });
      }),
    );
    renderRoutes(routes, ["/admin/students/new"]);
    fireEvent.click(
      await screen.findByRole("button", { name: texts.admin.students.form.submitCreate }),
    );
    expect(
      await screen.findByText(texts.admin.students.form.errors.nameRequired),
    ).toBeInTheDocument();
    expect(posted).toBe(false);
  });

  it("создание: отправляет данные и открывает карточку с приглашением", async () => {
    mockMe("manager");
    let body: unknown;
    server.use(
      http.post("*/api/v1/admin/students", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(managerCard, { status: 201 });
      }),
      http.get("*/api/v1/admin/students/7", () => HttpResponse.json(managerCard)),
      http.post("*/api/v1/admin/students/7/invitations", () =>
        HttpResponse.json(
          { id: 3, url: "https://t.me/bot?start=abc", expires_at: "2026-10-14T10:00:00Z" },
          { status: 201 },
        ),
      ),
    );
    const { router } = renderRoutes(routes, ["/admin/students/new"]);
    fireEvent.change(await screen.findByLabelText(texts.admin.students.form.name), {
      target: { value: "Аня Иванова" },
    });
    fireEvent.click(screen.getByRole("button", { name: texts.admin.students.form.submitCreate }));
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/admin/students/7");
    });
    expect(body).toMatchObject({ display_name: "Аня Иванова", timezone: "Europe/Moscow" });
    expect(await screen.findByDisplayValue("https://t.me/bot?start=abc")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: texts.admin.invitation.copy })).toBeInTheDocument();
  });
});
