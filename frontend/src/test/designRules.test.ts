/**
 * Автоматические пункты чек-листа docs/07 §11: проверяют исходники интерфейса целиком, чтобы
 * дизайн-система не расходилась на новых экранах (T8.04).
 */
import { describe, expect, it } from "vitest";

const SOURCES = import.meta.glob<string>("/src/**/*.{ts,tsx}", {
  query: "?raw",
  import: "default",
  eager: true,
});

/** Файлы экранов и компонентов: без тестов, сгенерированных типов и самих токенов. */
const files = Object.entries(SOURCES).filter(
  ([path]) => !/\.test\.tsx?$|schema\.d\.ts$|\/src\/test\//.test(path),
);

function offenders(pattern: RegExp, skip: (path: string) => boolean = () => false): string[] {
  return files
    .filter(([path]) => !skip(path))
    .flatMap(([path, source]) =>
      source
        .split("\n")
        .map((line, index) => ({ line, index }))
        .filter(({ line }) => pattern.test(line))
        .map(({ line, index }) => `${path}:${String(index + 1)} ${line.trim()}`),
    );
}

describe("дизайн-система: docs/07 §11", () => {
  it("цвета только через токены: нет hex, rgb() и hsl() в коде экранов", () => {
    expect(offenders(/#[0-9a-fA-F]{3,8}\b(?![^"']*\))|\brgba?\(|\bhsla?\(/)).toEqual([]);
  });

  it("нет backdrop-filter и drop-shadow", () => {
    expect(offenders(/backdrop-|drop-shadow|\bblur-|\bblur\(/)).toEqual([]);
  });

  it("нет цветов палитры Tailwind: только токены (адаптивны к тёмной теме)", () => {
    const palette =
      /\b(text|bg|border|ring|fill|stroke|from|to|via)-(gray|slate|zinc|neutral|stone|red|green|amber|orange|yellow|blue|white|black)(-\d+)?\b/;
    // боковое меню админки всегда на фоне brand-black: светло-серый текст там задан намеренно
    expect(offenders(palette, (path) => path.endsWith("/layouts/AdminLayout.tsx"))).toEqual([]);
  });

  it("радиусы из шкалы 8/12/16 (sm/md/lg) и full для маркеров", () => {
    expect(offenders(/\brounded-(xl|2xl|3xl|\[)/)).toEqual([]);
  });

  it("шрифты только через font-display, font-heading и font-body", () => {
    expect(offenders(/\bfont-(sans|serif|mono)\b|fontFamily/)).toEqual([]);
  });

  it("не больше одного амбер-элемента в файле экрана", () => {
    const skip = (path: string) => /components\/(ui\/button|common\/StatusBadge)/.test(path);
    const counts = files
      .filter(([path]) => !skip(path))
      .map(
        ([path, source]) =>
          [path, (source.match(/bg-highlight|variant="highlight"/g) ?? []).length] as const,
      )
      .filter(([, count]) => count > 1);
    expect(counts).toEqual([]);
  });
});

describe("тексты интерфейса: docs/07 §8.1", () => {
  const textsSource =
    Object.entries(SOURCES).find(([path]) => path.endsWith("/lib/texts.ts"))?.[1] ?? "";
  const strings = textsSource.match(/"(?:[^"\\\n]|\\.)*"|`(?:[^`\\]|\\.)*`/g) ?? [];

  it("файл текстов найден и не пуст", () => {
    expect(strings.length).toBeGreaterThan(100);
  });

  it("нет запрещённых слов и штампов", () => {
    const banned =
      /эксперт|профессионал|сертифицированн|индивидуальный подход|гарантия результата|топов|качественное образование/i;
    expect(strings.filter((text) => banned.test(text))).toEqual([]);
  });

  it("не больше одного «!» в строке", () => {
    expect(strings.filter((text) => (text.match(/!/g) ?? []).length > 1)).toEqual([]);
  });

  it("в интерфейсе нет эмодзи (только иконки)", () => {
    expect(strings.filter((text) => /\p{Extended_Pictographic}/u.test(text))).toEqual([]);
  });
});
