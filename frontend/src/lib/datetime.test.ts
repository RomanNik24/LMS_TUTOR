/**
 * Тесты форматирования даты/времени в поясе пользователя (docs/12 §8, §11).
 * Особое внимание — границам суток: момент 00:00 в одном поясе может быть
 * другим календарным днём в поясе пользователя.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  addMinutesIso,
  minutesUntil,
  dayStartUtcIso,
  daysBetween,
  formatDate,
  formatDayKey,
  isoWeekday,
  minutesBetween,
  shiftDayKey,
  toLocalParts,
  upcomingWeekdayKeys,
  weekDayKeys,
  weekStartKey,
  formatDayLabel,
  formatTime,
  formatTimeRange,
  localDayKey,
  localToUtcIso,
} from "@/lib/datetime";

describe("formatTime", () => {
  it("полночь UTC — это 03:00 следующего дня в Москве", () => {
    expect(formatTime("2026-10-14T00:00:00Z", "Europe/Moscow")).toBe("03:00");
  });

  it("последняя минута суток в поясе пользователя", () => {
    // 20:59 UTC = 23:59 MSK того же дня
    expect(formatTime("2026-10-14T20:59:00Z", "Europe/Moscow")).toBe("23:59");
  });

  it("учитывает пояс, а не время устройства", () => {
    // 23:00 UTC = 02:00 следующего дня в Екатеринбурге (UTC+5)
    expect(formatTime("2026-10-14T23:00:00Z", "Asia/Yekaterinburg")).toBe("04:00");
  });
});

describe("localDayKey — границы суток", () => {
  it("момент после полуночи пользователя относится к следующему дню", () => {
    // MSK = UTC+3: 21:30 UTC — это уже 00:30 следующего дня (15 октября)
    expect(localDayKey("2026-10-14T21:30:00Z", "Europe/Moscow")).toBe("2026-10-15");
  });

  it("20:59 UTC — ещё 14 октября в Москве", () => {
    expect(localDayKey("2026-10-14T20:59:00Z", "Europe/Moscow")).toBe("2026-10-14");
  });

  it("00:00 UTC — тот же день для Лондона (UTC+0 зимой)", () => {
    expect(localDayKey("2026-10-14T00:00:00Z", "Europe/London")).toBe("2026-10-14");
  });

  it("западнее UTC дата отстаёт: 01:00 UTC — ещё 13 октября в Нью-Йорке", () => {
    // Нью-Йорк зимой UTC−5, но 14 октября — ещё EDT (UTC−4): 01:00 UTC = 21:00 13.10
    expect(localDayKey("2026-10-14T01:00:00Z", "America/New_York")).toBe("2026-10-13");
  });
});

describe("formatDate / formatDayLabel — русская локаль", () => {
  it("форматирует дату по-русски в поясе пользователя", () => {
    // Перед «г.» — неразрывный пробел U+00A0 (типографика docs/07 §4)
    expect(formatDate("2026-10-14T21:30:00Z", "Europe/Moscow")).toBe("15 октября 2026\u00a0г.");
  });

  it("день недели тоже считается в поясе пользователя", () => {
    // 15 октября 2026 — четверг
    expect(formatDayLabel("2026-10-14T21:30:00Z", "Europe/Moscow")).toBe("четверг, 15 октября");
  });
});

describe("formatTimeRange", () => {
  it("склеивает начало и конец в поясе пользователя", () => {
    expect(formatTimeRange("2026-10-14T11:00:00Z", "2026-10-14T12:30:00Z", "Europe/Moscow")).toBe(
      "14:00–15:30",
    );
  });
});

describe("localToUtcIso — обратный перевод из пояса пользователя", () => {
  it("локальная полночь Москвы = 21:00 UTC предыдущего дня", () => {
    expect(localToUtcIso("2026-10-15", "00:00", "Europe/Moscow")).toBe("2026-10-14T21:00:00.000Z");
  });

  it("летнее время (Москва стабильно UTC+3) — та же формула", () => {
    expect(localToUtcIso("2026-07-01", "09:00", "Europe/Moscow")).toBe("2026-07-01T06:00:00.000Z");
  });

  it("бросает ошибку на неверном формате даты", () => {
    expect(() => localToUtcIso("2026-13", "09:00", "Europe/Moscow")).toThrowError();
  });
});

describe("дни и недели (T3.09)", () => {
  it("сдвиг дня переходит через границу месяца и високосный день", () => {
    expect(shiftDayKey("2026-10-31", 1)).toBe("2026-11-01");
    expect(shiftDayKey("2028-02-28", 1)).toBe("2028-02-29");
    expect(shiftDayKey("2028-03-01", -1)).toBe("2028-02-29");
    expect(shiftDayKey("2026-12-31", 1)).toBe("2027-01-01");
  });

  it("день недели ISO: понедельник = 1, воскресенье = 7", () => {
    expect(isoWeekday("2026-10-12")).toBe(1);
    expect(isoWeekday("2026-10-18")).toBe(7);
  });

  it("неделя начинается с понедельника", () => {
    expect(weekStartKey("2026-10-14")).toBe("2026-10-12");
    expect(weekStartKey("2026-10-18")).toBe("2026-10-12");
    expect(weekStartKey("2026-10-12")).toBe("2026-10-12");
    expect(weekDayKeys("2026-10-14")).toEqual([
      "2026-10-12",
      "2026-10-13",
      "2026-10-14",
      "2026-10-15",
      "2026-10-16",
      "2026-10-17",
      "2026-10-18",
    ]);
  });

  it("неделя через переход на зимнее время остаётся из 7 разных дней", () => {
    const keys = weekDayKeys("2026-10-25");
    expect(new Set(keys).size).toBe(7);
    expect(keys[0]).toBe("2026-10-19");
    expect(keys[6]).toBe("2026-10-25");
  });

  it("подпись дня по-русски", () => {
    expect(formatDayKey("2026-10-14")).toBe("ср, 14 окт");
  });

  it("начало суток в Москве и Екатеринбурге в UTC", () => {
    expect(dayStartUtcIso("2026-10-14", "Europe/Moscow")).toBe("2026-10-13T21:00:00.000Z");
    expect(dayStartUtcIso("2026-10-14", "Asia/Yekaterinburg")).toBe("2026-10-13T19:00:00.000Z");
  });

  it("начало суток в день перехода на летнее время в Берлине (UTC+1 → UTC+2)", () => {
    expect(dayStartUtcIso("2026-03-29", "Europe/Berlin")).toBe("2026-03-28T23:00:00.000Z");
    expect(dayStartUtcIso("2026-03-30", "Europe/Berlin")).toBe("2026-03-29T22:00:00.000Z");
  });

  it("длительность: прибавление минут и разница", () => {
    const end = addMinutesIso("2026-10-14T14:00:00.000Z", 90);
    expect(end).toBe("2026-10-14T15:30:00.000Z");
    expect(minutesBetween("2026-10-14T14:00:00.000Z", end)).toBe(90);
  });

  it("локальные дата и время для формы", () => {
    expect(toLocalParts("2026-10-14T21:30:00Z", "Europe/Moscow")).toEqual({
      date: "2026-10-15",
      time: "00:30",
    });
  });

  it("ближайшие даты шаблона: включительно, по неделям, с ограничением", () => {
    // 14 октября — среда; ближайшие вторники — 20 и 27 октября
    expect(upcomingWeekdayKeys("2026-10-14", 2, 3)).toEqual([
      "2026-10-20",
      "2026-10-27",
      "2026-11-03",
    ]);
    expect(upcomingWeekdayKeys("2026-10-13", 2, 2)).toEqual(["2026-10-13", "2026-10-20"]);
    expect(upcomingWeekdayKeys("2026-10-14", 2, 4, "2026-10-27")).toEqual([
      "2026-10-20",
      "2026-10-27",
    ]);
    expect(upcomingWeekdayKeys("2026-10-14", 2, 4, "2026-10-01")).toEqual([]);
  });

  it("число дней между ключами", () => {
    expect(daysBetween("2026-10-01", "2026-10-31")).toBe(30);
    expect(daysBetween("2026-10-31", "2026-10-01")).toBe(-30);
  });
});

describe("minutesUntil", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("считает минуты до момента и округляет вверх", () => {
    vi.useFakeTimers({ toFake: ["Date"], now: new Date("2026-10-14T12:00:00Z") });
    expect(minutesUntil("2026-10-14T14:15:00Z")).toBe(135);
    expect(minutesUntil("2026-10-14T12:00:30Z")).toBe(1);
  });

  it("для прошедшего момента — ноль или отрицательное", () => {
    vi.useFakeTimers({ toFake: ["Date"], now: new Date("2026-10-14T12:00:00Z") });
    expect(minutesUntil("2026-10-14T12:00:00Z")).toBe(0);
    expect(minutesUntil("2026-10-14T11:00:00Z")).toBe(-60);
  });
});
