import { describe, expect, it } from "vitest";

import {
  gradeFormSchema,
  homeworkFormSchema,
  returnFormSchema,
  toHomeworkPayload,
  toReturnPayload,
} from "./forms";
import type { HomeworkFormValues } from "./forms";

const valid: HomeworkFormValues = {
  title: " Задачи 1-5 ",
  description: "",
  subject_code: "informatics",
  max_score: "5",
  due_mode: "next_lesson",
  date: "2026-10-20",
  time: "20:00",
  student_ids: ["11", "12"],
};

const ok = (patch: Partial<HomeworkFormValues>) =>
  homeworkFormSchema.safeParse({ ...valid, ...patch }).success;

describe("homeworkFormSchema", () => {
  it("число заданий — целое от 1 до 100", () => {
    expect(ok({ max_score: "1" })).toBe(true);
    expect(ok({ max_score: "100" })).toBe(true);
    expect(ok({ max_score: "0" })).toBe(false);
    expect(ok({ max_score: "101" })).toBe(false);
    expect(ok({ max_score: "2.5" })).toBe(false);
    expect(ok({ max_score: "" })).toBe(false);
  });

  it("название и ученики обязательны", () => {
    expect(ok({ title: "   " })).toBe(false);
    expect(ok({ title: "а".repeat(256) })).toBe(false);
    expect(ok({ student_ids: [] })).toBe(false);
  });

  it("нужны дата и время срока", () => {
    expect(ok({ date: "" })).toBe(false);
    expect(ok({ time: "" })).toBe(false);
  });

  it("тело запроса: срок в UTC, пустое описание — null, id числами", () => {
    expect(toHomeworkPayload(homeworkFormSchema.parse(valid), "Europe/Moscow")).toEqual({
      kind: "regular",
      title: "Задачи 1-5",
      description: null,
      subject_code: "informatics",
      max_score: 5,
      due_mode: "next_lesson",
      due_at: "2026-10-20T17:00:00.000Z",
      student_ids: [11, 12],
    });
  });
});

describe("gradeFormSchema", () => {
  const schema = gradeFormSchema(13);
  const ok = (score: string, geometry_score = "") =>
    schema.safeParse({ score, comment: "", geometry_score }).success;

  it("балл — целое от 0 до максимума включительно", () => {
    expect(ok("0")).toBe(true);
    expect(ok("13")).toBe(true);
    expect(ok("14")).toBe(false);
    expect(ok("-1")).toBe(false);
    expect(ok("")).toBe(false);
    expect(ok("1.5")).toBe(false);
  });

  it("баллы по геометрии: пусто или целое неотрицательное", () => {
    expect(ok("5", "")).toBe(true);
    expect(ok("5", "2")).toBe(true);
    expect(ok("5", "-1")).toBe(false);
    expect(ok("5", "1.5")).toBe(false);
  });
});

describe("returnFormSchema", () => {
  const base = { comment: "Исправь №3", date: "", time: "" };

  it("комментарий обязателен, срок необязателен", () => {
    expect(returnFormSchema.safeParse(base).success).toBe(true);
    expect(returnFormSchema.safeParse({ ...base, comment: " " }).success).toBe(false);
  });

  it("дата без времени и время без даты отклоняются", () => {
    expect(returnFormSchema.safeParse({ ...base, date: "2026-10-20" }).success).toBe(false);
    expect(returnFormSchema.safeParse({ ...base, time: "20:00" }).success).toBe(false);
  });

  it("тело запроса: без срока — null, со сроком — UTC", () => {
    expect(toReturnPayload(returnFormSchema.parse(base), "Europe/Moscow")).toEqual({
      comment: "Исправь №3",
      new_due_at: null,
    });
    const withDue = returnFormSchema.parse({ ...base, date: "2026-10-20", time: "20:00" });
    expect(toReturnPayload(withDue, "Europe/Moscow").new_due_at).toBe("2026-10-20T17:00:00.000Z");
  });
});
