import { screen } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { routes } from "@/router";
import { renderRoutes } from "@/test/renderRoutes";
import { server } from "@/test/server";

describe("HelloPage после входа", () => {
  it.each([
    ["student", "Ученик"],
    ["manager", "Менеджер"],
    ["owner", "Владелец"],
  ] as const)("показывает «Привет, {имя}» и роль %s", async (role, label) => {
    server.use(
      http.get("*/api/v1/me", () =>
        HttpResponse.json({ id: 1, role, display_name: "Аня", timezone: "Europe/Moscow" }),
      ),
    );
    renderRoutes(routes, ["/"]);
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("Привет, Аня");
    expect(screen.getByText(`Роль: ${label}`)).toBeInTheDocument();
  });

  it("без входа отправляет на /login", async () => {
    server.use(
      http.get("*/api/v1/me", () =>
        HttpResponse.json(
          { error: { code: "unauthenticated", message: "x", details: {} } },
          { status: 401 },
        ),
      ),
    );
    const { router } = renderRoutes(routes, ["/"]);
    await screen.findByText("Войди через Telegram-бота");
    expect(router.state.location.pathname).toBe("/login");
  });
});
