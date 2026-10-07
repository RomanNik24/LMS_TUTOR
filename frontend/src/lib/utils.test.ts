import { describe, expect, it } from "vitest";

import { cn, initials } from "./utils";

describe("utils", () => {
  it("cn склеивает классы и разрешает конфликты tailwind", () => {
    expect(cn("p-2", false, "p-4")).toBe("p-4");
  });

  it("initials берёт первые буквы имени и фамилии", () => {
    expect(initials("Анна Петрова")).toBe("АП");
    expect(initials("Анна")).toBe("А");
  });
});
