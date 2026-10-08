import { screen } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderRoutes } from "@/test/renderRoutes";
import { server } from "@/test/server";

import { resetLaunchLoginForTests, useMe } from "./api";

const telegram = vi.hoisted(() => ({ miniApp: true }));
vi.mock("@/lib/telegram", () => ({
  isTelegramMiniApp: () => telegram.miniApp,
  getInitData: () => (telegram.miniApp ? "query_id=AAH&hash=abc" : null),
}));

const OWNER = { id: 3, role: "owner", display_name: "Владелец", timezone: "Europe/Moscow" };
const STUDENT = { id: 4, role: "student", display_name: "Ученик тест", timezone: "Europe/Moscow" };

function Who() {
  const { data } = useMe();
  return <p>{data?.display_name ?? "…"}</p>;
}

describe("useMe в Mini App", () => {
  beforeEach(() => {
    telegram.miniApp = true;
    resetLaunchLoginForTests();
  });

  it("входит по initData, даже если cookie остался от другого аккаунта", async () => {
    const calls: string[] = [];
    server.use(
      // cookie ученика: /me вернул бы ученика
      http.get("*/api/v1/me", () => {
        calls.push("GET /me");
        return HttpResponse.json(STUDENT);
      }),
      http.post("*/api/v1/auth/telegram", () => {
        calls.push("POST /auth/telegram");
        return HttpResponse.json(OWNER);
      }),
    );
    renderRoutes([{ path: "/", element: <Who /> }], ["/"]);

    expect(await screen.findByText("Владелец")).toBeInTheDocument();
    expect(calls).toEqual(["POST /auth/telegram"]);
  });

  it("вне Mini App берёт обычный GET /me", async () => {
    telegram.miniApp = false;
    server.use(http.get("*/api/v1/me", () => HttpResponse.json(STUDENT)));
    renderRoutes([{ path: "/", element: <Who /> }], ["/"]);

    expect(await screen.findByText("Ученик тест")).toBeInTheDocument();
  });
});
