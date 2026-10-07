/**
 * Форматирование даты/времени в часовом поясе пользователя (docs/12 §8, docs/06 B3).
 *
 * ВАЖНО: API присылает время в UTC (ISO-строка). Пользователь видит его в своём
 * поясе (me.timezone). Здесь НЕЛЬЗЯ использовать методы Date, зависящие от пояса
 * устройства (getHours, toLocaleString без timeZone) — вместо этого TZDate из
 * @date-fns/tz, который явно применяет пояс к каждому вычислению.
 */
import { addDays, addMinutes, format } from "date-fns";
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

// ---------------------------------------------------------------- дни и недели (T3.09)
// Ключ дня «yyyy-MM-dd» — календарная дата в поясе пользователя. Арифметика по дням ведётся в
// поясе UTC, поэтому она не зависит ни от пояса устройства, ни от перехода на летнее время.

const DAY_KEY = "yyyy-MM-dd";
const MS_IN_DAY = 86_400_000;

function parseDayKey(dayKey: string): TZDate {
  const [year, month, day] = dayKey.split("-").map(Number);
  if (year === undefined || month === undefined || day === undefined) {
    throw new Error(`Неверная дата: ${dayKey}`);
  }
  return new TZDate(year, month - 1, day, 12, 0, 0, "UTC");
}

/** Сегодняшний день в поясе пользователя: «2026-10-14». */
export function todayKey(timeZone: string): string {
  return format(new TZDate(new Date(), timeZone), DAY_KEY);
}

/** Сдвиг ключа дня на ``days`` дней (можно отрицательное). */
export function shiftDayKey(dayKey: string, days: number): string {
  return format(addDays(parseDayKey(dayKey), days), DAY_KEY);
}

/** День недели ISO для ключа дня: 1 = понедельник … 7 = воскресенье. */
export function isoWeekday(dayKey: string): number {
  const day = parseDayKey(dayKey).getDay();
  return day === 0 ? 7 : day;
}

/** Понедельник недели, в которую попадает день. */
export function weekStartKey(dayKey: string): string {
  return shiftDayKey(dayKey, 1 - isoWeekday(dayKey));
}

/** Семь ключей дней недели, начиная с понедельника. */
export function weekDayKeys(dayKey: string): string[] {
  const start = weekStartKey(dayKey);
  return Array.from({ length: 7 }, (_, index) => shiftDayKey(start, index));
}

/** Подпись дня по ключу: «пн, 12 окт». */
export function formatDayKey(dayKey: string): string {
  return format(parseDayKey(dayKey), "EEEEEE, d MMM", { locale: ru }).replace(".", "");
}

/** Подпись дня по ключу без сокращений: «понедельник, 12 октября». */
export function formatDayKeyLong(dayKey: string): string {
  return format(parseDayKey(dayKey), "EEEE, d MMMM", { locale: ru });
}

/** Начало суток ``dayKey`` в поясе пользователя как ISO-строка UTC. */
export function dayStartUtcIso(dayKey: string, timeZone: string): string {
  return localToUtcIso(dayKey, "00:00", timeZone);
}

/** Конец ISO-момента через ``minutes`` минут (для длительности урока). */
export function addMinutesIso(isoUtc: string, minutes: number): string {
  return addMinutes(new Date(isoUtc), minutes).toISOString();
}

/** Разница между двумя ISO-моментами в минутах. */
export function minutesBetween(startIsoUtc: string, endIsoUtc: string): number {
  return Math.round((new Date(endIsoUtc).getTime() - new Date(startIsoUtc).getTime()) / 60_000);
}

/** Дата «yyyy-MM-dd» и время «HH:mm» момента в поясе пользователя (для предзаполнения форм). */
export function toLocalParts(isoUtc: string, timeZone: string): { date: string; time: string } {
  const zoned = toTz(isoUtc, timeZone);
  return { date: format(zoned, DAY_KEY), time: format(zoned, "HH:mm") };
}

/**
 * Ближайшие ``count`` дат на день недели ISO, начиная с ``fromKey`` (включительно),
 * но не позже ``untilKey`` (если задан). Для предпросмотра шаблона расписания.
 */
export function upcomingWeekdayKeys(
  fromKey: string,
  isoWeekdayNumber: number,
  count: number,
  untilKey?: string,
): string[] {
  const first = shiftDayKey(fromKey, (isoWeekdayNumber - isoWeekday(fromKey) + 7) % 7);
  const result: string[] = [];
  for (let index = 0; index < count; index += 1) {
    const key = shiftDayKey(first, index * 7);
    if (untilKey !== undefined && key > untilKey) break;
    result.push(key);
  }
  return result;
}

/** Число дней между двумя ключами (``to`` − ``from``). */
export function daysBetween(fromKey: string, toKey: string): number {
  return Math.round((parseDayKey(toKey).getTime() - parseDayKey(fromKey).getTime()) / MS_IN_DAY);
}
