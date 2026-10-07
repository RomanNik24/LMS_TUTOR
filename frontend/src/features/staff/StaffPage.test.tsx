import { fireEvent, screen, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { routes } from "@/router";
import { texts } from "@/lib/texts";
import { mockMe } from "@/test/mockMe";
import { renderRoutes } from "@/test/renderRoutes";
import { server } from "@/test/server";

const staff = {
  user_id: 2,
  display_name: "Мария",
  role: "manager",
  timezone: "Europe/Moscow",
  is_active: true,
  bot_blocked: false,
  telegram_linked: false,
  invite_pending: true,
};

function mockStaff(items: unknown[]) {
  server.use(
    http.get("*/api/v1/admin/staff", () =>
      HttpResponse.json({ items, total: items.length, limit: 200, offset: 0 }),
    ),
  );
}

describe("Сотрудники", () => {
  it("владелец видит список с ролью и ожидающим приглашением", async () => {
    mockMe("owner");
    mockStaff([staff]);
    renderRoutes(routes, ["/admin/staff"]);
    expect(await screen.findByText("Мария")).toBeInTheDocument();
    expect(screen.getByText(texts.admin.staff.roles.manager)).toBeInTheDocument();
    expect(screen.getByText(texts.admin.staff.invitePending)).toBeInTheDocument();
  });

  it("менеджера на /admin/staff не пускают", async () => {
    mockMe("manager");
    const { router } = renderRoutes(routes, ["/admin/staff"]);
    await waitFor(() => {
      expect(router.state.location.pathname).not.toBe("/admin/staff");
    });
  });

  it("пустой список: подсказка", async () => {
    mockMe("owner");
    mockStaff([]);
    renderRoutes(routes, ["/admin/staff"]);
    expect(await screen.findByText(texts.admin.staff.empty.title)).toBeInTheDocument();
  });

  it("архивация требует подтверждения", async () => {
    mockMe("owner");
    mockStaff([staff]);
    let archived = false;
    server.use(
      http.post("*/api/v1/admin/staff/2/archive", () => {
        archived = true;
        return HttpResponse.json({ ...staff, is_active: false });
      }),
    );
    renderRoutes(routes, ["/admin/staff"]);
    fireEvent.click(await screen.findByRole("button", { name: texts.admin.staff.actions.archive }));
    expect(archived).toBe(false);
    fireEvent.click(await screen.findByRole("button", { name: texts.admin.staff.archiveConfirm }));
    await waitFor(() => {
      expect(archived).toBe(true);
    });
  });
});
