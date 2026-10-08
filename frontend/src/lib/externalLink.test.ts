import { describe, expect, it } from "vitest";

import { externalLinkProps, isSafeExternalUrl } from "./externalLink";

describe("isSafeExternalUrl", () => {
  it.each([
    "https://telemost.yandex.ru/j/123",
    "https://t.me/bot",
    "http://localhost:9000/file",
    "http://127.0.0.1:9000/file",
  ])("пропускает %s", (url) => {
    expect(isSafeExternalUrl(url)).toBe(true);
  });

  it.each([
    "http://example.com",
    "javascript:alert(1)",
    "data:text/html,<script>1</script>",
    "//evil.example",
    "ftp://example.com",
    "не ссылка",
    "",
  ])("блокирует %s", (url) => {
    expect(isSafeExternalUrl(url)).toBe(false);
  });
});

describe("externalLinkProps", () => {
  it("всегда открывает в новой вкладке без доступа к opener", () => {
    expect(externalLinkProps("https://t.me/bot")).toEqual({
      href: "https://t.me/bot",
      target: "_blank",
      rel: "noopener noreferrer",
    });
  });

  it("у небезопасного адреса нет href", () => {
    expect(externalLinkProps("javascript:alert(1)").href).toBeUndefined();
  });
});
