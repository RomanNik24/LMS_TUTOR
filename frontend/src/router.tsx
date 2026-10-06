/**
 * Маршруты (docs/12 §5.4). В T1.13 — только вход и страница «Привет»;
 * разделы /app/* и /admin/* появятся в следующих задачах.
 */
import { createBrowserRouter, createMemoryRouter, Navigate } from "react-router-dom";
import type { RouteObject } from "react-router-dom";

import { RequireRole } from "@/features/auth/RequireRole";
import { HelloPage } from "@/features/auth/pages/HelloPage";
import { LinkLoginPage } from "@/features/auth/pages/LinkLoginPage";
import { LoginPage } from "@/features/auth/pages/LoginPage";

export const routes: RouteObject[] = [
  { path: "/login", element: <LoginPage /> },
  { path: "/login/:token", element: <LinkLoginPage /> },
  {
    element: <RequireRole allowed={["student", "manager", "owner"]} />,
    children: [{ path: "/", element: <HelloPage /> }],
  },
  { path: "*", element: <Navigate to="/" replace /> },
];

export function createAppRouter() {
  return createBrowserRouter(routes);
}

/** Роутер в памяти — для тестов. */
export function createTestRouter(initialEntries: string[]) {
  return createMemoryRouter(routes, { initialEntries });
}
