import { Navigate, Outlet } from "react-router-dom";

import { errorMessage, isUnauthenticated } from "@/api/errors";
import { ErrorState } from "@/components/common/ErrorState";
import { FullScreenLoader } from "@/components/common/FullScreenLoader";

import { useMe } from "./api";
import type { Role } from "./api";

type RequireRoleProps = {
  allowed: readonly Role[];
};

/**
 * Защита маршрутов (docs/12 §5.3). Роль с сервера (GET /me) используется только для
 * навигации; настоящие права проверяет бэкенд.
 * Не вошёл (401) → /login; роль не подходит → /.
 */
export function RequireRole({ allowed }: RequireRoleProps) {
  const { data: me, isPending, error, refetch } = useMe();
  if (isPending) {
    return <FullScreenLoader />;
  }
  if (error !== null) {
    if (isUnauthenticated(error)) {
      return <Navigate to="/login" replace />;
    }
    // Сетевой сбой или 5xx: не выкидываем пользователя на экран входа
    return (
      <main className="flex min-h-dvh items-center justify-center bg-background">
        <ErrorState
          message={errorMessage(error)}
          onRetry={() => {
            void refetch();
          }}
        />
      </main>
    );
  }
  if (!allowed.includes(me.role)) {
    return <Navigate to="/" replace />;
  }
  return <Outlet />;
}
