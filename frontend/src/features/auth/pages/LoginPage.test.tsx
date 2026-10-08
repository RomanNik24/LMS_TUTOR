import { screen, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { texts } from "@/lib/texts";
import { renderRoutes } from "@/test/renderRoutes";
import { server } from "@/test/server";

import { LoginPage } from "./LoginPage";

// Telegram изолирован в lib/telegram.ts — подменяем его целиком (вне Telegram SDK не нужен)
const telegram = vi.hoisted(() => ({ miniApp: true, initData: "query_id=AAH&hash=abc" }));
vi.mock("@/lib/telegram", () => ({
  isTelegramMiniApp: () => telegram.miniApp,
  getInitData: () => (telegram.miniApp ? telegram.initData : null),
}));

const routes = [
  { path: "/login", element: <LoginPage /> },
  { path: "/", element: <p>страница после входа</p> },
];

const ME = { id: 7, role: "student", display_name: "Аня", timezone: "Europe/Moscow" };

function error(status: number, code: string) {
  return HttpResponse.json(
    { error: { code, message: "серверный текст", details: {} } },
    { status },
  );
}

describe("LoginPage", () => {
  beforeEach(() => {
    telegram.miniApp = true;
  });

  it("в Mini App отправляет initData на /auth/telegram один раз и уходит на /", async () => {
    const bodies: unknown[] = [];
    server.use(
      http.post("*/api/v1/auth/telegram", async ({ request }) => {
        bodies.push(await request.json());
        expect(request.headers.get("X-Requested-With")).toBe("XMLHttpRequest");
        return HttpResponse.json(ME);
      }),
    );
    const { router, queryClient } = renderRoutes(routes, ["/login"]);
    expect(screen.getByRole("status")).toBeInTheDocument(); // лоадер автовхода
    await screen.findByText("страница после входа");
    expect(router.state.location.pathname).toBe("/");
    expect(bodies).toEqual([{ init_data: telegram.initData }]);
    expect(queryClient.getQueryData(["me"])).toEqual(ME);
  });

  it("после входа возвращает на экран, куда шёл пользователь (ссылка из бота)", async () => {
    server.use(http.post("*/api/v1/auth/telegram", () => HttpResponse.json(ME)));
    const { router } = renderRoutes(
      [...routes, { path: "/app/homework/:id", element: <p>карточка ДЗ</p> }],
      [{ pathname: "/login", state: { from: "/app/homework/7" } }],
    );
    await screen.findByText("карточка ДЗ");
    expect(router.state.location.pathname).toBe("/app/homework/7");
  });

  it("чужой адрес возврата игнорируется: уходит на /", async () => {
    server.use(http.post("*/api/v1/auth/telegram", () => HttpResponse.json(ME)));
    const { router } = renderRoutes(routes, [
      { pathname: "/login", state: { from: "//evil.example" } },
    ]);
    await screen.findByText("страница после входа");
    expect(router.state.location.pathname).toBe("/");
  });

  it("ошибка входа показывает понятный текст и кнопку «Попробовать ещё раз»", async () => {
    let calls = 0;
    server.use(
      http.post("*/api/v1/auth/telegram", () => {
        calls += 1;
        return calls === 1 ? error(401, "unauthenticated") : HttpResponse.json(ME);
      }),
    );
    renderRoutes(routes, ["/login"]);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(texts.errors.unauthenticated);
    expect(alert).not.toHaveTextContent("серверный текст");
    screen.getByRole("button", { name: texts.login.retry }).click();
    await screen.findByText("страница после входа");
    expect(calls).toBe(2);
  });

  it("лимит запросов (429) объясняется пользователю", async () => {
    server.use(http.post("*/api/v1/auth/telegram", () => error(429, "rate_limited")));
    renderRoutes(routes, ["/login"]);
    expect(await screen.findByRole("alert")).toHaveTextContent(texts.errors.rate_limited);
  });

  it("вне Telegram запросов не делает и просит войти через бота", async () => {
    telegram.miniApp = false;
    // onUnhandledRequest: "error" в setup.ts уронил бы тест при любом запросе
    renderRoutes(routes, ["/login"]);
    expect(await screen.findByText(texts.login.openViaBot)).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByRole("status")).not.toBeInTheDocument();
    });
  });
});
