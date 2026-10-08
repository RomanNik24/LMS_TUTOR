import { screen, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { server } from "@/test/server";
import { renderRoutes } from "@/test/renderRoutes";
import { texts } from "@/lib/texts";

import { RequireRole } from "./RequireRole";
import type { Role } from "./api";

const routes = (allowed: Role[]) => [
  {
    element: <RequireRole allowed={allowed} />,
    children: [{ path: "/secret", element: <p>секретный раздел</p> }],
  },
  { path: "/login", element: <p>экран входа</p> },
  { path: "/", element: <p>главная</p> },
];

function mockMe(role: Role) {
  server.use(
    http.get("*/api/v1/me", () =>
      HttpResponse.json({ id: 1, role, display_name: "Аня", timezone: "Europe/Moscow" }),
    ),
  );
}

describe("RequireRole", () => {
  it("показывает лоадер, пока проверяется вход", () => {
    server.use(http.get("*/api/v1/me", () => new Promise<never>(() => undefined)));
    renderRoutes(routes(["owner"]), ["/secret"]);
    expect(screen.getByRole("status")).toHaveTextContent(texts.common.loading);
  });

  it("пускает пользователя с подходящей ролью", async () => {
    mockMe("owner");
    renderRoutes(routes(["owner", "manager"]), ["/secret"]);
    expect(await screen.findByText("секретный раздел")).toBeInTheDocument();
  });

  it("роль не подходит → редирект на /", async () => {
    mockMe("student");
    const { router } = renderRoutes(routes(["owner"]), ["/secret"]);
    expect(await screen.findByText("главная")).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/");
  });

  it("не вошёл (401) → редирект на /login", async () => {
    server.use(
      http.get("*/api/v1/me", () =>
        HttpResponse.json(
          { error: { code: "unauthenticated", message: "Требуется вход.", details: {} } },
          { status: 401 },
        ),
      ),
    );
    const { router } = renderRoutes(routes(["student"]), ["/secret"]);
    expect(await screen.findByText("экран входа")).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/login");
  });

  it("не вошёл → /login с запоминанием исходного адреса", async () => {
    server.use(
      http.get("*/api/v1/me", () =>
        HttpResponse.json(
          { error: { code: "unauthenticated", message: "Требуется вход.", details: {} } },
          { status: 401 },
        ),
      ),
    );
    const { router } = renderRoutes(routes(["student"]), ["/secret?tab=1"]);
    await screen.findByText("экран входа");
    expect(router.state.location.state).toEqual({ from: "/secret?tab=1" });
  });

  it("сбой сервера (500) не выбрасывает на экран входа, а показывает ошибку", async () => {
    server.use(
      http.get("*/api/v1/me", () =>
        HttpResponse.json(
          { error: { code: "internal_error", message: "x", details: {} } },
          { status: 500 },
        ),
      ),
    );
    const { router } = renderRoutes(routes(["student"]), ["/secret"]);
    expect(await screen.findByRole("alert")).toHaveTextContent(texts.errors.internal_error);
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/secret");
    });
  });
});
