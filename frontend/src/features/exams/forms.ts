/** Форма результата пробника (docs/07 §9.2.10): проверка полей и тело запроса к API. */
import { z } from "zod";

import type { ExamType } from "@/features/reference/api";
import { texts } from "@/lib/texts";

import type { ConvertRequest, MockExamCreate } from "./api";

const e = texts.admin.exams.form.errors;

export const COMMENT_MAX = 2000;
const INTEGER = /^\d+$/;

export const mockExamFormSchema = z
  .object({
    student_id: z.string().min(1, e.studentRequired),
    exam_type_id: z.string().min(1, e.examRequired),
    exam_date: z.string().min(1, e.dateRequired),
    primary_score: z.string().trim().regex(INTEGER, e.primaryRange),
    max_primary: z
      .string()
      .trim()
      .regex(INTEGER, e.maxRange)
      .refine((value) => Number(value) >= 1, e.maxRange),
    geometry_score: z.string().trim(),
    comment: z.string().trim().max(COMMENT_MAX, e.commentTooLong),
  })
  .superRefine((values, context) => {
    const primary = Number(values.primary_score);
    if (INTEGER.test(values.primary_score) && INTEGER.test(values.max_primary)) {
      if (primary > Number(values.max_primary)) {
        context.addIssue({ code: "custom", path: ["primary_score"], message: e.scoreAboveMax });
      }
    }
    if (values.geometry_score !== "") {
      if (!INTEGER.test(values.geometry_score)) {
        context.addIssue({ code: "custom", path: ["geometry_score"], message: e.geometryRange });
      } else if (INTEGER.test(values.primary_score) && Number(values.geometry_score) > primary) {
        context.addIssue({
          code: "custom",
          path: ["geometry_score"],
          message: e.geometryAbovePrimary,
        });
      }
    }
  });

export type MockExamFormValues = z.infer<typeof mockExamFormSchema>;

export const EMPTY_MOCK_EXAM_FORM: MockExamFormValues = {
  student_id: "",
  exam_type_id: "",
  exam_date: "",
  primary_score: "",
  max_primary: "",
  geometry_score: "",
  comment: "",
};

/**
 * Поля для предпросмотра конвертации или `null`, пока форма заполнена не полностью/неверно.
 * Баллы по геометрии отправляются только для экзамена с таким правилом.
 */
export function toConvertRequest(
  values: Pick<
    MockExamFormValues,
    "exam_type_id" | "exam_date" | "primary_score" | "max_primary" | "geometry_score"
  >,
  examTypes: ExamType[],
): ConvertRequest | null {
  const exam = examTypes.find((item) => String(item.id) === values.exam_type_id);
  if (exam === undefined || values.exam_date === "") return null;
  if (!INTEGER.test(values.primary_score) || !INTEGER.test(values.max_primary)) return null;
  const primary = Number(values.primary_score);
  const max = Number(values.max_primary);
  if (max < 1 || primary > max) return null;
  let geometry: number | null = null;
  if (exam.uses_geometry && values.geometry_score !== "") {
    if (!INTEGER.test(values.geometry_score) || Number(values.geometry_score) > primary) {
      return null;
    }
    geometry = Number(values.geometry_score);
  }
  return {
    exam_type_id: exam.id,
    exam_date: values.exam_date,
    primary_score: primary,
    max_primary: max,
    geometry_score: geometry,
  };
}

export function toCreatePayload(
  values: MockExamFormValues,
  request: ConvertRequest,
): MockExamCreate {
  const comment = values.comment.trim();
  return {
    ...request,
    student_id: Number(values.student_id),
    comment: comment === "" ? null : comment,
  };
}
