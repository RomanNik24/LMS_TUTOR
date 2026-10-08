import { describe, expect, it } from "vitest";

import type { ExamType } from "@/features/reference/api";
import { EXAM_TYPES } from "@/test/server";

import { mockExamFormSchema, toConvertRequest, toCreatePayload } from "./forms";
import type { MockExamFormValues } from "./forms";

const TYPES = EXAM_TYPES as ExamType[];

const valid: MockExamFormValues = {
  student_id: "11",
  exam_type_id: "3",
  exam_date: "2026-05-20",
  primary_score: "20",
  max_primary: "29",
  geometry_score: "",
  comment: "",
};

const ok = (patch: Partial<MockExamFormValues>) =>
  mockExamFormSchema.safeParse({ ...valid, ...patch }).success;

describe("mockExamFormSchema", () => {
  it("верная форма проходит", () => {
    expect(ok({})).toBe(true);
  });

  it("обязательны ученик, экзамен и дата", () => {
    expect(ok({ student_id: "" })).toBe(false);
    expect(ok({ exam_type_id: "" })).toBe(false);
    expect(ok({ exam_date: "" })).toBe(false);
  });

  it("первичный балл — целое от 0 и не больше максимума (границы)", () => {
    expect(ok({ primary_score: "0" })).toBe(true);
    expect(ok({ primary_score: "29" })).toBe(true);
    expect(ok({ primary_score: "30" })).toBe(false);
    expect(ok({ primary_score: "-1" })).toBe(false);
    expect(ok({ primary_score: "1.5" })).toBe(false);
    expect(ok({ primary_score: "" })).toBe(false);
  });

  it("максимум — целое от 1", () => {
    expect(ok({ max_primary: "27", primary_score: "20" })).toBe(true);
    expect(ok({ max_primary: "0", primary_score: "0" })).toBe(false);
    expect(ok({ max_primary: "" })).toBe(false);
  });

  it("баллы по геометрии: пусто или целое, не больше первичного балла", () => {
    expect(ok({ geometry_score: "" })).toBe(true);
    expect(ok({ geometry_score: "20" })).toBe(true);
    expect(ok({ geometry_score: "21" })).toBe(false);
    expect(ok({ geometry_score: "-1" })).toBe(false);
  });

  it("комментарий не длиннее 2000 символов", () => {
    expect(ok({ comment: "а".repeat(2000) })).toBe(true);
    expect(ok({ comment: "а".repeat(2001) })).toBe(false);
  });
});

describe("toConvertRequest", () => {
  it("собирает тело предпросмотра из полностью верной формы", () => {
    expect(toConvertRequest(valid, TYPES)).toEqual({
      exam_type_id: 3,
      exam_date: "2026-05-20",
      primary_score: 20,
      max_primary: 29,
      geometry_score: null,
    });
  });

  it("пока форма неполная или неверная — null (запрос не отправляется)", () => {
    expect(toConvertRequest({ ...valid, exam_type_id: "" }, TYPES)).toBeNull();
    expect(toConvertRequest({ ...valid, exam_date: "" }, TYPES)).toBeNull();
    expect(toConvertRequest({ ...valid, primary_score: "" }, TYPES)).toBeNull();
    expect(toConvertRequest({ ...valid, primary_score: "30" }, TYPES)).toBeNull();
    expect(toConvertRequest({ ...valid, max_primary: "0" }, TYPES)).toBeNull();
  });

  it("геометрия уходит только для экзамена с таким правилом", () => {
    const oge = { ...valid, exam_type_id: "2", max_primary: "31", geometry_score: "1" };
    expect(toConvertRequest(oge, TYPES)?.geometry_score).toBe(1);
    expect(toConvertRequest({ ...valid, geometry_score: "1" }, TYPES)?.geometry_score).toBeNull();
    expect(toConvertRequest({ ...oge, geometry_score: "21" }, TYPES)).toBeNull();
  });
});

describe("toCreatePayload", () => {
  it("добавляет ученика и комментарий (пустой — null)", () => {
    const request = toConvertRequest(valid, TYPES);
    if (request === null) throw new Error("форма верна");
    expect(toCreatePayload({ ...valid, comment: "  Вариант 3 " }, request)).toEqual({
      ...request,
      student_id: 11,
      comment: "Вариант 3",
    });
    expect(toCreatePayload(valid, request).comment).toBeNull();
  });
});
