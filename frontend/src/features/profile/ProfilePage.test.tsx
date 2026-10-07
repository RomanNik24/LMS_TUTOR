import { fireEvent, screen, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { routes } from "@/router";
import { texts } from "@/lib/texts";
import { mockMe } from "@/test/mockMe";
import { renderRoutes } from "@/test/renderRoutes";
import { server } from "@/test/server";

describe("Профиль ученика", () => {
  it("аватар в шапке ведёт в профиль", async () => {
    mockMe("student", "Аня Петрова");
    const { router } = renderRoutes(routes, ["/app/schedule"]);
    fireEvent.click(await screen.findByRole("link", { name: /Профиль: Аня Петрова/ }));
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/app/profile");
    });
  });

  it("смена часового пояса отправляет PATCH /me и обновляет профиль", async () => {
    mockMe("student", "Аня");
    let body: unknown;
    server.use(
      http.patch("*/api/v1/me", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({
          id: 1,
          role: "student",
          display_name: "Аня",
          timezone: "Asia/Omsk",
        });
      }),
    );
    renderRoutes(routes, ["/app/profile"]);
    const select = await screen.findByLabelText(texts.profile.timezone);
    fireEvent.change(select, { target: { value: "Asia/Omsk" } });
    fireEvent.click(screen.getByRole("button", { name: texts.profile.save }));
    await waitFor(() => {
      expect(body).toEqual({ display_name: "Аня", timezone: "Asia/Omsk" });
    });
    await waitFor(() => {
      expect(screen.getByLabelText(texts.profile.timezone)).toHaveValue("Asia/Omsk");
    });
  });

  it("пустое имя не отправляется", async () => {
    mockMe("student", "Аня");
    let sent = false;
    server.use(
      http.patch("*/api/v1/me", () => {
        sent = true;
        return HttpResponse.json({});
      }),
    );
    renderRoutes(routes, ["/app/profile"]);
    fireEvent.change(await screen.findByLabelText(texts.profile.name), { target: { value: "  " } });
    fireEvent.click(screen.getByRole("button", { name: texts.profile.save }));
    expect(await screen.findByText(texts.profile.nameRequired)).toBeInTheDocument();
    expect(sent).toBe(false);
  });

  it("нестандартный пояс пользователя остаётся в списке", async () => {
    server.use(
      http.get("*/api/v1/me", () =>
        HttpResponse.json({ id: 1, role: "student", display_name: "Аня", timezone: "Asia/Tokyo" }),
      ),
    );
    renderRoutes(routes, ["/app/profile"]);
    expect(await screen.findByLabelText(texts.profile.timezone)).toHaveValue("Asia/Tokyo");
  });

  it("есть подсказка про вход в браузере и выход", async () => {
    mockMe("student");
    renderRoutes(routes, ["/app/profile"]);
    expect(await screen.findByText(texts.profile.webLogin)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: texts.profile.logout })).toBeInTheDocument();
  });
});
