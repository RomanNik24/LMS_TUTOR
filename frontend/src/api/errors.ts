/**
 * Ошибки API (docs/12 §4.3). Бэкенд отвечает `{"error": {"code", "message", "details"}}`
 * (docs/08 §1); здесь это превращается в исключение ApiError, а код ошибки — в
 * понятный пользователю текст из texts.ts.
 */
import { texts } from "@/lib/texts";
import type { ErrorTextKey } from "@/lib/texts";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

/** Результат вызова openapi-fetch (нужные нам поля). */
export type FetchResult<T> = {
  data?: T;
  error?: unknown;
  response: Response;
};

const UNKNOWN_CODE = "unknown_error";

function isRecord(value: unknown): value is Partial<Record<string, unknown>> {
  return typeof value === "object" && value !== null;
}

/** Достаёт code/message из тела ошибки без доверия к его форме (unknown → проверки). */
export function parseErrorBody(body: unknown): { code: string; message: string } {
  const error = isRecord(body) ? body["error"] : undefined;
  if (!isRecord(error)) {
    return { code: UNKNOWN_CODE, message: texts.errors.unknown };
  }
  const code = typeof error["code"] === "string" ? error["code"] : UNKNOWN_CODE;
  const message = typeof error["message"] === "string" ? error["message"] : texts.errors.unknown;
  return { code, message };
}

function toApiError(result: FetchResult<unknown>): ApiError {
  const { code, message } = parseErrorBody(result.error);
  return new ApiError(result.response.status, code, message);
}

/** Возвращает данные ответа или бросает ApiError (для ответов с телом). */
export function unwrap<T>(result: FetchResult<T>): T {
  if (result.error !== undefined || result.data === undefined) {
    throw toApiError(result);
  }
  return result.data;
}

/** Для ответов без тела (204): бросает ApiError только при ошибке. */
export function unwrapEmpty(result: FetchResult<unknown>): void {
  if (result.error !== undefined) {
    throw toApiError(result);
  }
}

function isErrorTextKey(code: string): code is ErrorTextKey {
  return Object.prototype.hasOwnProperty.call(texts.errors, code);
}

/**
 * Понятный текст для пользователя: по коду ошибки из texts.ts; сетевые сбои
 * (fetch бросает TypeError) — отдельный текст; остальное — общий.
 */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return isErrorTextKey(error.code) ? texts.errors[error.code] : texts.errors.unknown;
  }
  if (error instanceof TypeError) {
    return texts.errors.network;
  }
  return texts.errors.unknown;
}

/** 401 — «не вошёл»: это нормальное состояние, а не сбой. */
export function isUnauthenticated(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401;
}
