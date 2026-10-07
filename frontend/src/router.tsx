/**
 * Маршруты (docs/12 §5.4): вход, страница «Привет», Student App (`/app/*`) и Admin App (`/admin/*`).
 * Админская часть подгружается лениво (React.lazy): ученику её код не нужен.
 * Разделы без данных показывают «пустое состояние» (`SectionPlaceholder`) — их заменят экраны этапов 2–8.
 */
import {
  BookOpen,
  CalendarDays,
  ClipboardCheck,
  ClipboardList,
  LineChart,
  Sun,
  UserCog,
  Users,
  Wallet,
} from "lucide-react";
import { Suspense, lazy } from "react";
import { createBrowserRouter, createMemoryRouter, Navigate } from "react-router-dom";
import type { RouteObject } from "react-router-dom";

import { FullScreenLoader } from "@/components/common/FullScreenLoader";
import { RequireRole } from "@/features/auth/RequireRole";
import { HelloPage } from "@/features/auth/pages/HelloPage";
import { LinkLoginPage } from "@/features/auth/pages/LinkLoginPage";
import { LoginPage } from "@/features/auth/pages/LoginPage";
import { StudentLayout } from "@/layouts/StudentLayout";
import { texts } from "@/lib/texts";
import { MorePage } from "@/pages/MorePage";
import { SectionPlaceholder } from "@/pages/SectionPlaceholder";

const AdminLayout = lazy(() =>
  import("@/layouts/AdminLayout").then((module) => ({ default: module.AdminLayout })),
);

function LazyAdminLayout() {
  return (
    <Suspense fallback={<FullScreenLoader />}>
      <AdminLayout />
    </Suspense>
  );
}

const studentRoutes: RouteObject = {
  path: "/app",
  element: <RequireRole allowed={["student"]} />,
  children: [
    {
      element: <StudentLayout />,
      children: [
        { index: true, element: <Navigate to="schedule" replace /> },
        {
          path: "schedule",
          element: (
            <SectionPlaceholder
              icon={CalendarDays}
              title={texts.empty.studentSchedule.title}
              text={texts.empty.studentSchedule.text}
            />
          ),
        },
        {
          path: "homework",
          element: (
            <SectionPlaceholder
              icon={ClipboardList}
              title={texts.empty.studentHomework.title}
              text={texts.empty.studentHomework.text}
            />
          ),
        },
        {
          path: "reports",
          element: (
            <SectionPlaceholder
              icon={LineChart}
              title={texts.empty.studentReports.title}
              text={texts.empty.studentReports.text}
            />
          ),
        },
      ],
    },
  ],
};

const soon = (title: string, icon: typeof Sun) => (
  <SectionPlaceholder icon={icon} title={title} text={texts.empty.soon} />
);

const adminRoutes: RouteObject = {
  path: "/admin",
  element: <RequireRole allowed={["owner", "manager"]} />,
  children: [
    {
      element: <LazyAdminLayout />,
      children: [
        { index: true, element: <Navigate to="today" replace /> },
        { path: "today", element: soon(texts.nav.admin.today, Sun) },
        { path: "schedule", element: soon(texts.nav.admin.schedule, CalendarDays) },
        {
          path: "homework",
          element: (
            <SectionPlaceholder
              icon={ClipboardList}
              title={texts.empty.adminReviewQueue.title}
              text={texts.empty.adminReviewQueue.text}
            />
          ),
        },
        {
          path: "students",
          element: (
            <SectionPlaceholder
              icon={Users}
              title={texts.empty.adminStudents.title}
              text={texts.empty.adminStudents.text}
            />
          ),
        },
        { path: "more", element: <MorePage /> },
        { path: "exams", element: soon(texts.nav.admin.exams, ClipboardCheck) },
        { path: "catalog", element: soon(texts.nav.admin.catalog, BookOpen) },
        {
          element: <RequireRole allowed={["owner"]} />,
          children: [
            { path: "finance", element: soon(texts.nav.admin.finance, Wallet) },
            { path: "staff", element: soon(texts.nav.admin.staff, UserCog) },
          ],
        },
      ],
    },
  ],
};

export const routes: RouteObject[] = [
  { path: "/login", element: <LoginPage /> },
  { path: "/login/:token", element: <LinkLoginPage /> },
  {
    element: <RequireRole allowed={["student", "manager", "owner"]} />,
    children: [{ path: "/", element: <HelloPage /> }],
  },
  studentRoutes,
  adminRoutes,
  { path: "*", element: <Navigate to="/" replace /> },
];

export function createAppRouter() {
  return createBrowserRouter(routes);
}

/** Роутер в памяти — для тестов. */
export function createTestRouter(initialEntries: string[]) {
  return createMemoryRouter(routes, { initialEntries });
}
