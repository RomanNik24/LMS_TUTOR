import type { Role } from "./api";

/** Куда попадает пользователь, если конкретный экран не запрошен. */
export function homePath(role: Role): string {
  return role === "student" ? "/app/schedule" : "/admin/today";
}

/**
 * Адрес возврата после входа (откуда пользователя отправили на /login): только внутренний путь
 * приложения. Внешние адреса, `//host`, `javascript:` и сам экран входа отбрасываются: иначе
 * ссылка вида `/login` с чужим `from` стала бы открытым редиректом.
 */
export function safeReturnPath(value: unknown): string | null {
  if (typeof value !== "string") return null;
  if (!value.startsWith("/") || value.startsWith("//") || value.includes("\\")) return null;
  if (value === "/login" || value.startsWith("/login/") || value.startsWith("/login?")) return null;
  return value;
}

/** Состояние навигации, которое RequireRole передаёт экрану входа. */
export type LoginLocationState = { from?: string };

export function returnPathFrom(state: unknown): string | null {
  if (typeof state !== "object" || state === null) return null;
  return safeReturnPath((state as LoginLocationState).from);
}
