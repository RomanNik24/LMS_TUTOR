/** Схема формы ученика (docs/07 §9.2.4) и перевод значений формы в тело запроса API. */
import { z } from "zod";

import type { components } from "@/api/schema";
import { texts } from "@/lib/texts";

const e = texts.admin.students.form.errors;

export const SCHOOL_CLASS_MIN = 1;
export const SCHOOL_CLASS_MAX = 11;
export const NAME_MAX_LENGTH = 150;
export const URL_MAX_LENGTH = 500;
export const NOTES_MAX_LENGTH = 5000;
export const PRICE_MAX = 1_000_000;

/** Коды предметов (справочник subjects); каталог предметов в админке появится позже. */
export const SUBJECT_CODES = ["informatics", "math"] as const;
export const TIMEZONES = Object.keys(texts.admin.timezones);
export const DEFAULT_TIMEZONE = "Europe/Moscow";

const httpsUrl = z
  .string()
  .trim()
  .max(URL_MAX_LENGTH, e.urlTooLong)
  .refine((value) => value === "" || /^https:\/\/\S+$/.test(value), e.urlHttps);

export const studentFormSchema = z.object({
  display_name: z.string().trim().min(1, e.nameRequired).max(NAME_MAX_LENGTH, e.nameTooLong),
  school_class: z
    .string()
    .trim()
    .refine((value) => {
      if (value === "") return true;
      const n = Number(value);
      return Number.isInteger(n) && n >= SCHOOL_CLASS_MIN && n <= SCHOOL_CLASS_MAX;
    }, e.classRange),
  subject_codes: z.array(z.string()),
  timezone: z.string().min(1, e.timezoneRequired),
  video_url: httpsUrl,
  board_url: httpsUrl,
  lesson_price: z
    .string()
    .trim()
    .refine((value) => {
      if (value === "") return true;
      const n = Number(value);
      return /^\d+$/.test(value) && n >= 0 && n <= PRICE_MAX;
    }, e.priceRange),
  teacher_notes: z.string().max(NOTES_MAX_LENGTH, e.notesTooLong),
});

export type StudentFormValues = z.infer<typeof studentFormSchema>;

export const EMPTY_STUDENT_FORM: StudentFormValues = {
  display_name: "",
  school_class: "",
  subject_codes: [],
  timezone: DEFAULT_TIMEZONE,
  video_url: "",
  board_url: "",
  lesson_price: "",
  teacher_notes: "",
};

type StudentCreate = components["schemas"]["StudentCreate"];
type StudentUpdate = components["schemas"]["StudentUpdate"];

const orNull = (value: string): string | null => {
  const trimmed = value.trim();
  return trimmed === "" ? null : trimmed;
};

/** Цену отправляет только владелец и только если поле заполнено. */
function priceFields(values: StudentFormValues, canEditPrice: boolean): { lesson_price?: number } {
  if (!canEditPrice || values.lesson_price.trim() === "") return {};
  return { lesson_price: Number(values.lesson_price) };
}

export function toCreatePayload(values: StudentFormValues, canEditPrice: boolean): StudentCreate {
  return {
    display_name: values.display_name.trim(),
    timezone: values.timezone,
    school_class: values.school_class.trim() === "" ? null : Number(values.school_class),
    subject_codes: values.subject_codes,
    video_url: orNull(values.video_url),
    board_url: orNull(values.board_url),
    teacher_notes: orNull(values.teacher_notes),
    ...priceFields(values, canEditPrice),
  };
}

export function toUpdatePayload(values: StudentFormValues, canEditPrice: boolean): StudentUpdate {
  return toCreatePayload(values, canEditPrice);
}

type Card = components["schemas"]["StudentCardOwner"] | components["schemas"]["StudentCardManager"];

export function cardToFormValues(card: Card): StudentFormValues {
  return {
    display_name: card.display_name,
    school_class: card.school_class === null ? "" : String(card.school_class),
    subject_codes: card.subjects,
    timezone: card.timezone,
    video_url: card.video_url ?? "",
    board_url: card.board_url ?? "",
    lesson_price: "lesson_price" in card ? String(card.lesson_price) : "",
    teacher_notes: card.teacher_notes ?? "",
  };
}
