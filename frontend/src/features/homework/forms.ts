/** Схемы форм ДЗ и перевод значений формы в тела запросов (срок — в UTC). */
import { z } from "zod";

import { localToUtcIso } from "@/lib/datetime";
import { texts } from "@/lib/texts";

import type { HomeworkCreate, ReturnRequest } from "./api";

const e = texts.admin.homework.form.errors;
const r = texts.admin.homework.review.errors;

export const TITLE_MAX = 255;
export const DESCRIPTION_MAX = 5000;
export const MAX_SCORE_LIMIT = 100;
export const DEFAULT_DUE_TIME = "20:00";

const dateField = (message: string) => z.string().regex(/^\d{4}-\d{2}-\d{2}$/, message);
const timeField = (message: string) => z.string().regex(/^\d{2}:\d{2}$/, message);

export const homeworkFormSchema = z
  .object({
    title: z.string().trim().min(1, e.nameRequired).max(TITLE_MAX, e.nameTooLong),
    description: z.string().trim().max(DESCRIPTION_MAX, e.descriptionTooLong),
    subject_code: z.string().min(1),
    max_score: z
      .string()
      .trim()
      .refine((value) => {
        const n = Number(value);
        return /^\d+$/.test(value) && n >= 1 && n <= MAX_SCORE_LIMIT;
      }, e.maxScoreRange),
    due_mode: z.enum(["next_lesson", "fixed"]),
    date: z.string(),
    time: z.string(),
    student_ids: z.array(z.string()).min(1, e.studentsRequired),
  })
  .superRefine((values, context) => {
    // Дата обязательна при «Дата»; при «Следующее занятие» это запасной срок — тоже нужен.
    if (!/^\d{4}-\d{2}-\d{2}$/.test(values.date)) {
      context.addIssue({ code: "custom", path: ["date"], message: e.dateRequired });
    }
    if (!/^\d{2}:\d{2}$/.test(values.time)) {
      context.addIssue({ code: "custom", path: ["time"], message: e.timeRequired });
    }
  });
export type HomeworkFormValues = z.infer<typeof homeworkFormSchema>;

export function toHomeworkPayload(values: HomeworkFormValues, timeZone: string): HomeworkCreate {
  const description = values.description.trim();
  return {
    kind: "regular",
    title: values.title.trim(),
    description: description === "" ? null : description,
    subject_code: values.subject_code,
    max_score: Number(values.max_score),
    due_mode: values.due_mode,
    due_at: localToUtcIso(values.date, values.time, timeZone),
    student_ids: values.student_ids.map(Number),
  };
}

/** Оценка: целое от 0 до максимума (граница известна только после загрузки выдачи). */
export function gradeFormSchema(maxScore: number) {
  return z.object({
    score: z
      .string()
      .trim()
      .refine((value) => /^\d+$/.test(value) && Number(value) <= maxScore, r.scoreRange(maxScore)),
    comment: z.string().trim().max(DESCRIPTION_MAX, r.commentTooLong),
  });
}
export type GradeFormValues = z.infer<ReturnType<typeof gradeFormSchema>>;

export const returnFormSchema = z
  .object({
    comment: z.string().trim().min(1, r.commentRequired).max(DESCRIPTION_MAX, r.commentTooLong),
    date: z.string(),
    time: z.string(),
  })
  .superRefine((values, context) => {
    // Срок необязателен, но если начали вводить — нужны и дата, и время.
    if (values.date !== "" && values.time === "") {
      context.addIssue({ code: "custom", path: ["time"], message: r.timeRequired });
    }
    if (values.date === "" && values.time !== "") {
      context.addIssue({ code: "custom", path: ["date"], message: r.dateRequired });
    }
  });
export type ReturnFormValues = z.infer<typeof returnFormSchema>;

export function toReturnPayload(values: ReturnFormValues, timeZone: string): ReturnRequest {
  return {
    comment: values.comment.trim(),
    new_due_at:
      values.date === "" || values.time === ""
        ? null
        : localToUtcIso(values.date, values.time, timeZone),
  };
}

export const manualDueSchema = z.object({
  date: dateField(r.dateRequired),
  time: timeField(r.timeRequired),
});
export type ManualDueValues = z.infer<typeof manualDueSchema>;
