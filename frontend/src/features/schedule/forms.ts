/** Схемы форм расписания и перевод значений формы в тела запросов (время — в UTC). */
import { z } from "zod";

import { addMinutesIso, localToUtcIso } from "@/lib/datetime";
import { texts } from "@/lib/texts";

import type { LessonCreate, LessonReschedule, TemplateCreate } from "./api";

const e = texts.admin.schedule.form.errors;

export const DEFAULT_DURATION = "60";
export const DURATION_MIN = 1;
export const DURATION_MAX = 720;
export const MAX_PARTICIPANTS = 20;
export const TOPIC_MAX = 255;

const httpsUrl = z
  .string()
  .trim()
  .max(500, e.urlHttps)
  .refine((value) => value === "" || /^https:\/\/\S+$/.test(value), e.urlHttps);

const duration = z
  .string()
  .trim()
  .refine((value) => {
    const n = Number(value);
    return /^\d+$/.test(value) && n >= DURATION_MIN && n <= DURATION_MAX;
  }, e.durationRange);

const participants = z
  .array(z.string())
  .min(1, e.participantsRequired)
  .max(MAX_PARTICIPANTS, e.participantsTooMany);

const dateField = z.string().regex(/^\d{4}-\d{2}-\d{2}$/, e.dateRequired);
const timeField = z.string().regex(/^\d{2}:\d{2}$/, e.timeRequired);

export const lessonFormSchema = z.object({
  subject_code: z.string().min(1, e.subjectRequired),
  student_ids: participants,
  date: dateField,
  time: timeField,
  duration,
  video_url_override: httpsUrl,
  board_url_override: httpsUrl,
  topic: z.string().trim().max(TOPIC_MAX, e.topicTooLong),
});
export type LessonFormValues = z.infer<typeof lessonFormSchema>;

export const rescheduleFormSchema = z.object({ date: dateField, time: timeField, duration });
export type RescheduleFormValues = z.infer<typeof rescheduleFormSchema>;

export const templateFormSchema = z.object({
  subject_code: z.string().min(1, e.subjectRequired),
  student_ids: participants,
  weekday: z.string().regex(/^[1-7]$/),
  time: timeField,
  duration,
  starts_on: dateField,
  ends_on: z.string().refine((value) => value === "" || /^\d{4}-\d{2}-\d{2}$/.test(value)),
});
export type TemplateFormValues = z.infer<typeof templateFormSchema>;

const orNull = (value: string): string | null => {
  const trimmed = value.trim();
  return trimmed === "" ? null : trimmed;
};

export function interval(
  values: { date: string; time: string; duration: string },
  timeZone: string,
): { start_at: string; end_at: string } {
  const start = localToUtcIso(values.date, values.time, timeZone);
  return { start_at: start, end_at: addMinutesIso(start, Number(values.duration)) };
}

export function toLessonPayload(values: LessonFormValues, timeZone: string): LessonCreate {
  return {
    subject_code: values.subject_code,
    student_ids: values.student_ids.map(Number),
    ...interval(values, timeZone),
    video_url_override: orNull(values.video_url_override),
    board_url_override: orNull(values.board_url_override),
    topic: orNull(values.topic),
  };
}

export function toReschedulePayload(
  values: RescheduleFormValues,
  timeZone: string,
): LessonReschedule {
  return interval(values, timeZone);
}

export function toTemplatePayload(values: TemplateFormValues, timeZone: string): TemplateCreate {
  return {
    subject_code: values.subject_code,
    student_ids: values.student_ids.map(Number),
    weekday: Number(values.weekday),
    start_local_time: `${values.time}:00`,
    duration_minutes: Number(values.duration),
    timezone: timeZone,
    starts_on: values.starts_on,
    ends_on: values.ends_on === "" ? null : values.ends_on,
  };
}
