import { describe, expect, it } from "vitest";

import { initSentry, scrubEvent, scrubUrl } from "./sentry";

describe("scrubUrl", () => {
  it("убирает запрос и фрагмент (в них initData и токены)", () => {
    expect(scrubUrl("https://app.example/app/schedule?tgWebAppData=abc&x=1#tgWebAppData=zzz")).toBe(
      "https://app.example/app/schedule",
    );
  });

  it("заменяет токен входа в пути", () => {
    expect(scrubUrl("https://app.example/login/AbCdEfGhIjKlMnOpQrStUvWx12")).toBe(
      "https://app.example/login/[token]",
    );
  });

  it("обычные пути не трогает", () => {
    expect(scrubUrl("/admin/students/12")).toBe("/admin/students/12");
  });
});

describe("scrubEvent", () => {
  it("удаляет пользователя, контексты, extra, cookie и заголовки", () => {
    const event = scrubEvent({
      user: { id: "1", username: "anya" },
      extra: { initData: "query_id=1" },
      contexts: { device: {} },
      request: {
        url: "https://app.example/login/AbCdEfGhIjKlMnOpQrStUvWx12?x=1",
        cookies: { session_id: "secret" },
        headers: { Cookie: "session_id=secret" },
        data: "body",
      },
      transaction: "/login/AbCdEfGhIjKlMnOpQrStUvWx12",
      breadcrumbs: [
        { message: "go /login/AbCdEfGhIjKlMnOpQrStUvWx12", data: { url: "/x?token=1", body: "b" } },
      ],
    });

    expect(event).toEqual({
      request: { url: "https://app.example/login/[token]" },
      transaction: "/login/[token]",
      breadcrumbs: [{ message: "go /login/[token]", data: { url: "/x" } }],
    });
    expect(JSON.stringify(event)).not.toMatch(/secret|anya|query_id|body/);
  });

  it("без request не добавляет его", () => {
    expect(scrubEvent({ user: { id: "1" } })).toEqual({});
  });
});

describe("initSentry", () => {
  it.each([undefined, "", "   "])("без DSN (%j) ничего не загружает", async (dsn) => {
    expect(await initSentry(dsn)).toBe(false);
  });
});
