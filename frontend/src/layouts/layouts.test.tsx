import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { texts } from "@/lib/texts";
import { routes } from "@/router";
import { mockMe } from "@/test/mockMe";
import { renderRoutes } from "@/test/renderRoutes";
import { setViewport } from "@/test/viewport";

describe("StudentLayout", () => {
  it.each([360, 1280])("показывает нижнюю панель из трёх пунктов при %i px", async (width) => {
    setViewport(width);
    mockMe("student");
    renderRoutes(routes, ["/app/schedule"]);
    const nav = await screen.findByRole("navigation", { name: texts.common.mainNavigation });
    expect(nav.querySelectorAll("a")).toHaveLength(3);
  });

  it("ученик не попадает в админку", async () => {
    mockMe("student");
    const { router } = renderRoutes(routes, ["/admin/today"]);
    await waitFor(() => {
      expect(router.state.location.pathname).not.toMatch(/^\/admin/);
    });
  });
});

describe("AdminLayout", () => {
  it("мобильный вид: таб-бар из 5 пунктов", async () => {
    setViewport(360);
    mockMe("manager");
    renderRoutes(routes, ["/admin/today"]);
    const nav = await screen.findByRole("navigation", { name: texts.common.mainNavigation });
    expect(nav.querySelectorAll("a")).toHaveLength(5);
  });

  it("планшет: компактное меню с подписями-иконками", async () => {
    setViewport(800);
    mockMe("manager");
    renderRoutes(routes, ["/admin/today"]);
    const link = await screen.findByRole("link", { name: texts.nav.admin.students });
    expect(link).toHaveAttribute("title", texts.nav.admin.students);
  });

  it("десктоп: полный сайдбар; менеджер не видит финансы и сотрудников", async () => {
    setViewport(1280);
    mockMe("manager");
    renderRoutes(routes, ["/admin/today"]);
    expect(await screen.findByRole("link", { name: texts.nav.admin.catalog })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: texts.nav.admin.finance })).toBeNull();
    expect(screen.queryByRole("link", { name: texts.nav.admin.staff })).toBeNull();
  });

  it("десктоп: владелец видит финансы и сотрудников", async () => {
    setViewport(1280);
    mockMe("owner");
    renderRoutes(routes, ["/admin/today"]);
    expect(await screen.findByRole("link", { name: texts.nav.admin.finance })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: texts.nav.admin.staff })).toBeInTheDocument();
  });

  it("менеджер по прямому адресу /admin/finance уходит с раздела", async () => {
    setViewport(1280);
    mockMe("manager");
    const { router } = renderRoutes(routes, ["/admin/finance"]);
    await waitFor(() => {
      expect(router.state.location.pathname).not.toBe("/admin/finance");
    });
  });
});
