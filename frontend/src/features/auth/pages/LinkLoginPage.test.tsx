import { fireEvent, screen } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { texts } from "@/lib/texts";
import { renderRoutes } from "@/test/renderRoutes";
import { server } from "@/test/server";

import { LinkLoginPage } from "./LinkLoginPage";

const routes = [
  { path: "/login/:token", element: <LinkLoginPage /> },
  { path: "/", element: <p>страница после входа</p> },
];

const ME = { id: 3, role: "owner", display_name: "Роман", timezone: "Europe/Moscow" };

function error(status: number, code: string) {
  return HttpResponse.json({ error: { code, message: "x", details: {} } }, { status });
}

describe("LinkLoginPage (/login/:token)", () => {
  it("открытие страницы (GET) токен не гасит: запросов нет, пока не нажата «Войти»", async () => {
    let posts = 0;
    server.use(
      http.post("*/api/v1/auth/link", () => {
        posts += 1;
        return HttpResponse.json(ME);
      }),
    );
    renderRoutes(routes, ["/login/abc123"]);
    expect(screen.getByText(texts.login.linkHint)).toBeInTheDocument();
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(posts).toBe(0);
  });

  it("по нажатию «Войти» отправляет токен POST-запросом и открывает приложение", async () => {
    const bodies: unknown[] = [];
    server.use(
      http.post("*/api/v1/auth/link", async ({ request }) => {
        bodies.push(await request.json());
        expect(request.headers.get("X-Requested-With")).toBe("XMLHttpRequest");
        return HttpResponse.json(ME);
      }),
    );
    const { queryClient } = renderRoutes(routes, ["/login/abc123"]);
    fireEvent.click(screen.getByRole("button", { name: texts.login.linkButton }));
    await screen.findByText("страница после входа");
    expect(bodies).toEqual([{ token: "abc123" }]);
    expect(queryClient.getQueryData(["me"])).toEqual(ME);
  });

  it("недействительная ссылка: «Попроси новую у Романа»", async () => {
    server.use(http.post("*/api/v1/auth/link", () => error(404, "login_link_invalid")));
    renderRoutes(routes, ["/login/bad"]);
    fireEvent.click(screen.getByRole("button", { name: texts.login.linkButton }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Ссылка недействительна или устарела. Попроси новую у Романа.",
    );
  });

  it("уже использованная ссылка", async () => {
    server.use(http.post("*/api/v1/auth/link", () => error(409, "invite_already_used")));
    renderRoutes(routes, ["/login/used"]);
    fireEvent.click(screen.getByRole("button", { name: texts.login.linkButton }));
    expect(await screen.findByRole("alert")).toHaveTextContent(texts.errors.invite_already_used);
  });

  it("кнопка блокируется на время запроса (защита от двойного нажатия)", async () => {
    let posts = 0;
    server.use(
      http.post("*/api/v1/auth/link", async () => {
        posts += 1;
        await new Promise((resolve) => setTimeout(resolve, 100));
        return HttpResponse.json(ME);
      }),
    );
    renderRoutes(routes, ["/login/abc"]);
    const button = screen.getByRole("button", { name: texts.login.linkButton });
    fireEvent.click(button);
    expect(await screen.findByRole("button", { name: texts.login.signingIn })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: texts.login.signingIn }));
    await screen.findByText("страница после входа");
    expect(posts).toBe(1);
  });
});
