/**
 * Тесты форматирования даты/времени в поясе пользователя (docs/12 §8, §11).
 * Особое внимание — границам суток: момент 00:00 в одном поясе может быть
 * другим календарным днём в поясе пользователя.
 */
import { describe, expect, it } from "vitest";

import {
  formatDate,
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
