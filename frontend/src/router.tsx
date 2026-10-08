/**
 * Маршруты (docs/12 §5.4): вход, страница «Привет», Student App (`/app/*`) и Admin App (`/admin/*`).
 * Админская часть и её страницы подгружаются лениво (React.lazy): ученику их код не нужен.
 */
import { Suspense, lazy } from "react";
import type { ComponentType, LazyExoticComponent } from "react";
import { createBrowserRouter, createMemoryRouter, Navigate } from "react-router-dom";
import type { RouteObject } from "react-router-dom";

import { FullScreenLoader } from "@/components/common/FullScreenLoader";
import { PageSkeleton } from "@/components/common/PageSkeleton";
import { RequireRole } from "@/features/auth/RequireRole";
import { HelloPage } from "@/features/auth/pages/HelloPage";
import { LinkLoginPage } from "@/features/auth/pages/LinkLoginPage";
import { LoginPage } from "@/features/auth/pages/LoginPage";
import { StudentHomeworkCardPage } from "@/features/homework/student/StudentHomeworkCardPage";
import { StudentHomeworkPage } from "@/features/homework/student/StudentHomeworkPage";
import { ProfilePage } from "@/features/profile/ProfilePage";
import { StudentLessonPage } from "@/features/schedule/StudentLessonPage";
import { StudentSchedulePage } from "@/features/schedule/StudentSchedulePage";
import { StudentLayout } from "@/layouts/StudentLayout";
import { MorePage } from "@/pages/MorePage";

const AdminLayout = lazy(() =>
  import("@/layouts/AdminLayout").then((module) => ({ default: module.AdminLayout })),
);

/**
 * Страница админки, загружаемая по требованию (React.lazy): ученику код админских экранов не нужен,
 * основной бандл остаётся небольшим (аудит 2026-10-08, п. 8). Пока код грузится, показывается
 * скелетон страницы.
 */
function withSkeleton(Page: LazyExoticComponent<ComponentType>) {
  return function LazyPage() {
    return (
      <Suspense fallback={<PageSkeleton />}>
        <Page />
      </Suspense>
    );
  };
}

const StudentReportsPage = withSkeleton(
  lazy(() =>
    import("@/features/reports/StudentReportsPage").then((module) => ({
      default: module.StudentReportsPage,
    })),
  ),
);
const CatalogPage = withSkeleton(
  lazy(() =>
    import("@/features/catalog/CatalogPage").then((module) => ({ default: module.CatalogPage })),
  ),
);
const DashboardPage = withSkeleton(
  lazy(() =>
    import("@/features/dashboard/DashboardPage").then((module) => ({
      default: module.DashboardPage,
    })),
  ),
);
const FinancePage = withSkeleton(
  lazy(() =>
    import("@/features/finance/FinancePage").then((module) => ({ default: module.FinancePage })),
  ),
);
const AdminExamsPage = withSkeleton(
  lazy(() =>
    import("@/features/exams/AdminExamsPage").then((module) => ({
      default: module.AdminExamsPage,
    })),
  ),
);
const AdminHomeworkPage = withSkeleton(
  lazy(() =>
    import("@/features/homework/AdminHomeworkPage").then((module) => ({
      default: module.AdminHomeworkPage,
    })),
  ),
);
const HomeworkDetailPage = withSkeleton(
  lazy(() =>
    import("@/features/homework/HomeworkDetailPage").then((module) => ({
      default: module.HomeworkDetailPage,
    })),
  ),
);
const ReviewPage = withSkeleton(
  lazy(() =>
    import("@/features/homework/ReviewPage").then((module) => ({ default: module.ReviewPage })),
  ),
);
const SchedulePage = withSkeleton(
  lazy(() =>
    import("@/features/schedule/SchedulePage").then((module) => ({ default: module.SchedulePage })),
  ),
);
const StaffPage = withSkeleton(
  lazy(() =>
    import("@/features/staff/StaffPage").then((module) => ({ default: module.StaffPage })),
  ),
);
const StudentCardPage = withSkeleton(
  lazy(() =>
    import("@/features/students/StudentCardPage").then((module) => ({
      default: module.StudentCardPage,
    })),
  ),
);
const StudentFormPage = withSkeleton(
  lazy(() =>
    import("@/features/students/StudentFormPage").then((module) => ({
      default: module.StudentFormPage,
    })),
  ),
);
const StudentsListPage = withSkeleton(
  lazy(() =>
    import("@/features/students/StudentsListPage").then((module) => ({
      default: module.StudentsListPage,
    })),
  ),
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
        { path: "profile", element: <ProfilePage /> },
        { path: "schedule", element: <StudentSchedulePage /> },
        { path: "schedule/:lessonId", element: <StudentLessonPage /> },
        { path: "homework", element: <StudentHomeworkPage /> },
        { path: "homework/:assignmentId", element: <StudentHomeworkCardPage /> },
        { path: "reports", element: <StudentReportsPage /> },
      ],
    },
  ],
};

const adminRoutes: RouteObject = {
  path: "/admin",
  element: <RequireRole allowed={["owner", "manager"]} />,
  children: [
    {
      element: <LazyAdminLayout />,
      children: [
        { index: true, element: <Navigate to="today" replace /> },
        { path: "today", element: <DashboardPage /> },
        { path: "schedule", element: <SchedulePage /> },
        { path: "homework", element: <AdminHomeworkPage /> },
        { path: "homework/:homeworkId", element: <HomeworkDetailPage /> },
        { path: "assignments/:assignmentId", element: <ReviewPage /> },
        { path: "students", element: <StudentsListPage /> },
        { path: "students/new", element: <StudentFormPage /> },
        { path: "students/:id", element: <StudentCardPage /> },
        { path: "students/:id/edit", element: <StudentFormPage /> },
        { path: "more", element: <MorePage /> },
        { path: "exams", element: <AdminExamsPage /> },
        { path: "catalog", element: <CatalogPage /> },
        {
          element: <RequireRole allowed={["owner"]} />,
          children: [
            { path: "finance", element: <FinancePage /> },
            { path: "staff", element: <StaffPage /> },
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
