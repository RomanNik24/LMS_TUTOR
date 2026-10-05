/**
 * ВСЕ тексты интерфейса живут здесь (docs/12 §10.2, docs/06 B3).
 * Язык — русский, идентификаторы — английские.
 * Пока минимальный набор ключей для каркаса; расширяется по мере появления экранов.
 */
export const texts = {
  app: {
    title: "Ромчик",
    greeting: "Привет, Ромчик",
  },
} as const;

/**
 * Формы множественного числа (docs/12 §10.2): plural(2, ["урок", "урока", "уроков"]) → "урока".
 * Русские правила: 1 → f1; 2–4 (кроме 12–14) → f2; иначе f3.
 */
export function plural(count: number, forms: readonly [string, string, string]): string {
  const n = Math.abs(count) % 100;
  const one = n % 10;
  if (n >= 11 && n <= 14) return forms[2];
  if (one === 1) return forms[0];
  if (one >= 2 && one <= 4) return forms[1];
  return forms[2];
}
