import { clsx } from "clsx";
import type { ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Склейка классов Tailwind без конфликтов (стандартная функция shadcn/ui). */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/** Инициалы для аватара: до двух первых букв слов имени («Анна Петрова» → «АП»). */
export function initials(name: string): string {
  const letters = name
    .trim()
    .split(/\s+/)
    .filter((word) => word.length > 0)
    .slice(0, 2)
    .map((word) => word.charAt(0).toUpperCase());
  return letters.join("");
}
