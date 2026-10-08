import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { mockMe } from "@/test/mockMe";
import { renderRoutes } from "@/test/renderRoutes";

import { HomeRedirect } from "./HomeRedirect";

const routes = [
  { path: "/", element: <HomeRedirect /> },
  { path: "/app/schedule", element: <p>расписание ученика</p> },
  { path: "/admin/today", element: <p>сегодня</p> },
];

describe("HomeRedirect", () => {
  it("ученика ведёт на расписание", async () => {
    mockMe("student");
    const { router } = renderRoutes(routes, ["/"]);
    await screen.findByText("расписание ученика");
    expect(router.state.location.pathname).toBe("/app/schedule");
  });

  it.each(["manager", "owner"] as const)("%s ведёт на «Сегодня»", async (role) => {
    mockMe(role);
    const { router } = renderRoutes(routes, ["/"]);
    await screen.findByText("сегодня");
    expect(router.state.location.pathname).toBe("/admin/today");
  });
});
