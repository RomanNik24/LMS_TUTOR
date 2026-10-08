import { describe, expect, it } from "vitest";

import { homePath, returnPathFrom, safeReturnPath } from "./redirect";

describe("homePath", () => {
  it("ученик — расписание, персонал — «Сегодня»", () => {
    expect(homePath("student")).toBe("/app/schedule");
    expect(homePath("manager")).toBe("/admin/today");
    expect(homePath("owner")).toBe("/admin/today");
  });
});

describe("safeReturnPath", () => {
  it.each(["/app/homework/7", "/admin/assignments/3?tab=files", "/"])("пропускает %s", (path) => {
    expect(safeReturnPath(path)).toBe(path);
  });

  it.each([
    "https://evil.example",
    "//evil.example",
    "/\\evil.example",
    "javascript:alert(1)",
    "app/homework",
    "/login",
    "/login/abc",
    "",
    null,
    undefined,
    42,
  ])("отбрасывает %j", (value) => {
    expect(safeReturnPath(value)).toBeNull();
  });
});

describe("returnPathFrom", () => {
  it("читает from из состояния навигации", () => {
    expect(returnPathFrom({ from: "/app/homework/7" })).toBe("/app/homework/7");
    expect(returnPathFrom({ from: "//evil" })).toBeNull();
    expect(returnPathFrom(null)).toBeNull();
    expect(returnPathFrom("x")).toBeNull();
  });
});
