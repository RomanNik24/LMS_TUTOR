/**
 * Форматирование даты/времени в часовом поясе пользователя (docs/12 §8, docs/06 B3).
 *
 * ВАЖНО: API присылает время в UTC (ISO-строка). Пользователь видит его в своём
 * поясе (me.timezone). Здесь НЕЛЬЗЯ использовать методы Date, зависящие от пояса
 * устройства (getHours, toLocaleString без timeZone) — вместо этого TZDate из
 * @date-fns/tz, который явно применяет пояс к каждому вычислению.
 */
import { format } from "date-fns";
import { ru } from "date-fns/locale";
import { TZDate } from "@date-fns/tz";

/** Ключ дня в поясе пользователя: "2026-10-14" (для группировки уроков по дням). */
export function localDayKey(isoUtc: string, timeZone: string): string {
  return format(toTz(isoUtc, timeZone), "yyyy-MM-dd");
}

/** Время «14:30» в поясе пользователя. */
export function formatTime(isoUtc: string, timeZone: string): string {
  return format(toTz(isoUtc, timeZone), "HH:mm", { locale: ru });
}

/** Диапазон «14:00–15:30» (оба конца в поясе пользователя). */
export function formatTimeRange(startIsoUtc: string, endIsoUtc: string, timeZone: string): string {
  return `${formatTime(startIsoUtc, timeZone)}–${formatTime(endIsoUtc, timeZone)}`;
}

/** Дата «14 октября 2026 г.» в поясе пользователя. */
export function formatDate(isoUtc: string, timeZone: string): string {
  // Неразрывный пробел U+00A0 перед «г.» — по типографике docs/07 §4;
  // сам суффикс дописываем строкой, а не литералом формата (кавычки date-fns
  // в разных версиях трактует нестабильно).
  return `${format(toTz(isoUtc, timeZone), "d MMMM yyyy", { locale: ru })}\u00a0г.`;
}

/** День недели и дата «среда, 14 октября» в поясе пользователя. */
export function formatDayLabel(isoUtc: string, timeZone: string): string {
  return format(toTz(isoUtc, timeZone), "EEEE, d MMMM", { locale: ru });
}

/**
 * Перевод локального времени, которое выбрал пользователь в своём поясе,
 * в ISO-строку UTC для отправки на сервер (docs/12 §6: формы отправляем в UTC).
 * timeOfDay — "HH:mm", date — "yyyy-MM-dd" (локальные, в поясе timeZone).
 */
export function localToUtcIso(date: string, timeOfDay: string, timeZone: string): string {
  const [year, month, day] = date.split("-").map(Number);
  const [hours, minutes] = timeOfDay.split(":").map(Number);
  // noUncheckedIndexedAccess: значения могут быть undefined — проверяем явно.
  if (year === undefined || month === undefined || day === undefined) {
    throw new Error(`Неверная дата: ${date}`);
  }
  if (hours === undefined || minutes === undefined) {
    throw new Error(`Неверное время: ${timeOfDay}`);
  }
  // TZDate строит момент «как если бы эти числа были временем в поясе timeZone»,
  // getTime() даёт абсолютный timestamp, toISOString() — канонический UTC-вид.
  const tzDate = new TZDate(year, month - 1, day, hours, minutes, 0, timeZone);
  return new Date(tzDate.getTime()).toISOString();
}

// Единая точка превращения ISO-UTC строки в момент в поясе пользователя.
function toTz(isoUtc: string, timeZone: string): TZDate {
  return new TZDate(new Date(isoUtc), timeZone);
}
