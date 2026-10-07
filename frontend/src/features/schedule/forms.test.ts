import { describe, expect, it } from "vitest";

import {
  lessonFormSchema,
  rescheduleFormSchema,
  templateFormSchema,
  toLessonPayload,
  toReschedulePayload,
  toTemplatePayload,
} from "./forms";
import type { LessonFormValues } from "./forms";

const valid: LessonFormValues = {
  subject_code: "informatics",
  student_ids: ["3"],
  date: "2026-10-14",
  time: "17:00",
  duration: "60",
  video_url_override: "",
  board_url_override: "",
  topic: "",
};

const ok = (patch: Partial<LessonFormValues>) =>
  lessonFormSchema.safeParse({ ...valid, ...patch }).success;

describe("lessonFormSchema: границы значений", () => {
  it("длительность 1–720 минут, только целое", () => {
    expect(ok({ duration: "1" })).toBe(true);
    expect(ok({ duration: "720" })).toBe(true);
    for (const bad of ["0", "721", "-5", "1.5", "", "abc"]) {
      expect(ok({ duration: bad })).toBe(false);
    }
  });

  it("участники: от 1 до 20", () => {
    expect(ok({ student_ids: [] })).toBe(false);
    expect(ok({ student_ids: Array.from({ length: 20 }, (_, i) => String(i + 1)) })).toBe(true);
    expect(ok({ student_ids: Array.from({ length: 21 }, (_, i) => String(i + 1)) })).toBe(false);
  });

  it("ссылки только https, пустая допустима", () => {
    expect(ok({ video_url_override: "https://telemost.yandex.ru/j/1" })).toBe(true);
    expect(ok({ board_url_override: "http://miro.com" })).toBe(false);
    expect(ok({ board_url_override: "javascript:alert(1)" })).toBe(false);
  });

  it("дата и время обязательны, тема до 255 символов", () => {
    expect(ok({ date: "" })).toBe(false);
    expect(ok({ time: "" })).toBe(false);
    expect(ok({ topic: "а".repeat(255) })).toBe(true);
    expect(ok({ topic: "а".repeat(256) })).toBe(false);
  });
});

describe("перевод значений формы в тело запроса", () => {
  it("время из пояса пользователя переводится в UTC", () => {
    const moscow = toLessonPayload(valid, "Europe/Moscow");
    expect(moscow.start_at).toBe("2026-10-14T14:00:00.000Z");
    expect(moscow.end_at).toBe("2026-10-14T15:00:00.000Z");
    const yekat = toLessonPayload({ ...valid, duration: "90" }, "Asia/Yekaterinburg");
    expect(yekat.start_at).toBe("2026-10-14T12:00:00.000Z");
    expect(yekat.end_at).toBe("2026-10-14T13:30:00.000Z");
  });

  it("летнее время Берлина: 17:00 — 15:00 UTC летом и 16:00 UTC зимой", () => {
    const summer = toLessonPayload({ ...valid, date: "2026-10-24" }, "Europe/Berlin");
    const winter = toLessonPayload({ ...valid, date: "2026-10-26" }, "Europe/Berlin");
    expect(summer.start_at).toBe("2026-10-24T15:00:00.000Z");
    expect(winter.start_at).toBe("2026-10-26T16:00:00.000Z");
  });

  it("участники превращаются в числа, пустые поля — в null", () => {
    const payload = toLessonPayload(
      { ...valid, student_ids: ["3", "5"], topic: "  " },
      "Europe/Moscow",
    );
    expect(payload.student_ids).toEqual([3, 5]);
    expect(payload.topic).toBeNull();
    expect(payload.video_url_override).toBeNull();
  });

  it("перенос использует ту же логику", () => {
    expect(
      toReschedulePayload({ date: "2026-10-15", time: "10:30", duration: "45" }, "Europe/Moscow"),
    ).toEqual({ start_at: "2026-10-15T07:30:00.000Z", end_at: "2026-10-15T08:15:00.000Z" });
    expect(
      rescheduleFormSchema.safeParse({ date: "2026-10-15", time: "10:30", duration: "0" }).success,
    ).toBe(false);
  });

  it("шаблон: день недели, время «на часах», пояс пользователя и период", () => {
    const payload = toTemplatePayload(
      {
        subject_code: "math",
        student_ids: ["2"],
        weekday: "2",
        time: "17:00",
        duration: "60",
        starts_on: "2026-10-20",
        ends_on: "",
      },
      "Europe/Moscow",
    );
    expect(payload).toMatchObject({
      weekday: 2,
      start_local_time: "17:00:00",
      timezone: "Europe/Moscow",
      starts_on: "2026-10-20",
      ends_on: null,
      duration_minutes: 60,
    });
    expect(
      templateFormSchema.safeParse({ ...payload, weekday: "9", time: "17:00", duration: "60" })
        .success,
    ).toBe(false);
  });
});
