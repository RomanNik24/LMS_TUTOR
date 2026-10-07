import { describe, expect, it } from "vitest";

import { EMPTY_STUDENT_FORM, studentFormSchema, toCreatePayload } from "./studentForm";
import type { StudentFormValues } from "./studentForm";

const valid = (patch: Partial<StudentFormValues> = {}): StudentFormValues => ({
  ...EMPTY_STUDENT_FORM,
  display_name: "Аня",
  ...patch,
});

const ok = (patch: Partial<StudentFormValues>) => studentFormSchema.safeParse(valid(patch)).success;

describe("studentFormSchema: границы значений", () => {
  it("имя: обязательно, не длиннее 150", () => {
    expect(ok({ display_name: "" })).toBe(false);
    expect(ok({ display_name: "   " })).toBe(false);
    expect(ok({ display_name: "а".repeat(150) })).toBe(true);
    expect(ok({ display_name: "а".repeat(151) })).toBe(false);
  });

  it("класс: пусто или целое 1–11", () => {
    expect(ok({ school_class: "" })).toBe(true);
    expect(ok({ school_class: "1" })).toBe(true);
    expect(ok({ school_class: "11" })).toBe(true);
    expect(ok({ school_class: "0" })).toBe(false);
    expect(ok({ school_class: "12" })).toBe(false);
    expect(ok({ school_class: "5.5" })).toBe(false);
    expect(ok({ school_class: "abc" })).toBe(false);
  });

  it("ссылки: только https://", () => {
    expect(ok({ video_url: "" })).toBe(true);
    expect(ok({ video_url: "https://telemost.yandex.ru/j/1" })).toBe(true);
    expect(ok({ board_url: "http://example.com" })).toBe(false);
    expect(ok({ board_url: "javascript:alert(1)" })).toBe(false);
    expect(ok({ video_url: `https://a.ru/${"a".repeat(500)}` })).toBe(false);
  });

  it("цена: пусто или целое 0–1 000 000", () => {
    expect(ok({ lesson_price: "" })).toBe(true);
    expect(ok({ lesson_price: "0" })).toBe(true);
    expect(ok({ lesson_price: "1000000" })).toBe(true);
    expect(ok({ lesson_price: "1000001" })).toBe(false);
    expect(ok({ lesson_price: "-1" })).toBe(false);
    expect(ok({ lesson_price: "1.5" })).toBe(false);
  });

  it("заметки: не длиннее 5000", () => {
    expect(ok({ teacher_notes: "а".repeat(5000) })).toBe(true);
    expect(ok({ teacher_notes: "а".repeat(5001) })).toBe(false);
  });
});

describe("toCreatePayload", () => {
  it("менеджер не отправляет цену, даже если поле заполнено", () => {
    const payload = toCreatePayload(valid({ lesson_price: "1500" }), false);
    expect("lesson_price" in payload).toBe(false);
  });

  it("владелец отправляет цену; пустые поля становятся null", () => {
    const payload = toCreatePayload(valid({ lesson_price: "1500", school_class: "9" }), true);
    expect(payload.lesson_price).toBe(1500);
    expect(payload.school_class).toBe(9);
    expect(payload.video_url).toBeNull();
    expect(payload.teacher_notes).toBeNull();
  });
});
