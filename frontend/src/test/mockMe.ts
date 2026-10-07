import { HttpResponse, http } from "msw";

import type { Role } from "@/features/auth/api";

import { server } from "./server";

/** Подменяет `GET /api/v1/me`: пользователь с заданной ролью и именем. */
export function mockMe(role: Role, displayName = "Анна Петрова"): void {
  server.use(
    http.get("*/api/v1/me", () =>
      HttpResponse.json({ id: 1, role, display_name: displayName, timezone: "Europe/Moscow" }),
    ),
  );
}
