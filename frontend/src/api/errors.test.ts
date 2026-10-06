import { describe, expect, it } from "vitest";

import { texts } from "@/lib/texts";

import {
  ApiError,
  errorMessage,
  isUnauthenticated,
  parseErrorBody,
  unwrap,
  unwrapEmpty,
} from "./errors";

function response(status: number): Response {
  return new Response(null, { status });
}

describe("unwrap", () => {
  it("возвращает данные успешного ответа", () => {
    expect(unwrap({ data: { id: 1 }, response: response(200) })).toEqual({ id: 1 });
  });

  it("бросает ApiError с кодом и сообщением бэкенда", () => {
    const body = { error: { code: "rate_limited", message: "Слишком много запросов" } };
    try {
      unwrap({ error: body, response: response(429) });
      expect.unreachable("ожидалась ошибка");
    } catch (error) {
      expect(error).toBeInstanceOf(ApiError);
      expect(error).toMatchObject({ status: 429, code: "rate_limited" });
    }
  });

  it("бросает ApiError, если нет ни данных, ни ошибки", () => {
    expect(() => unwrap({ response: response(200) })).toThrow(ApiError);
  });

  it("при неожиданном теле ошибки использует unknown_error", () => {
    try {
      unwrap({ error: "<html>502</html>", response: response(502) });
      expect.unreachable("ожидалась ошибка");
    } catch (error) {
      expect(error).toMatchObject({ status: 502, code: "unknown_error" });
    }
  });
});

describe("unwrapEmpty", () => {
  it("не бросает для ответа 204 без тела", () => {
    expect(() => unwrapEmpty({ response: response(204) })).not.toThrow();
  });

  it("бросает ApiError при ошибке", () => {
    const error = { error: { code: "unauthenticated", message: "x" } };
    expect(() => unwrapEmpty({ error, response: response(401) })).toThrow(ApiError);
  });
});

describe("parseErrorBody", () => {
  it.each([null, undefined, 42, "text", [], { error: "x" }, { error: null }])(
    "не падает на %j",
    (body) => {
      expect(parseErrorBody(body)).toEqual({
        code: "unknown_error",
        message: texts.errors.unknown,
      });
    },
  );

  it("игнорирует поля неверного типа", () => {
    expect(parseErrorBody({ error: { code: 5, message: {} } })).toEqual({
      code: "unknown_error",
      message: texts.errors.unknown,
    });
  });
});

describe("errorMessage", () => {
  it("сопоставляет известный код с текстом из texts.ts", () => {
    const error = new ApiError(404, "login_link_invalid", "raw");
    expect(errorMessage(error)).toBe(texts.errors.login_link_invalid);
    expect(errorMessage(new ApiError(401, "unauthenticated", "raw"))).toBe(
      texts.errors.unauthenticated,
    );
  });

  it("неизвестный код — общий текст, сырое сообщение сервера не показывается", () => {
    const text = errorMessage(new ApiError(400, "some_new_code", "Внутренняя причина"));
    expect(text).toBe(texts.errors.unknown);
    expect(text).not.toContain("Внутренняя");
  });

  it("код не должен совпадать со служебными свойствами объекта", () => {
    expect(errorMessage(new ApiError(400, "toString", "x"))).toBe(texts.errors.unknown);
  });

  it("сетевой сбой (TypeError от fetch)", () => {
    expect(errorMessage(new TypeError("Failed to fetch"))).toBe(texts.errors.network);
  });

  it("прочее", () => {
    expect(errorMessage(new Error("boom"))).toBe(texts.errors.unknown);
    expect(errorMessage("строка")).toBe(texts.errors.unknown);
  });
});

describe("isUnauthenticated", () => {
  it("true только для ApiError со статусом 401", () => {
    expect(isUnauthenticated(new ApiError(401, "unauthenticated", "x"))).toBe(true);
    expect(isUnauthenticated(new ApiError(403, "permission_denied", "x"))).toBe(false);
    expect(isUnauthenticated(new Error("x"))).toBe(false);
  });
});
