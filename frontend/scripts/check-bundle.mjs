/**
 * Бюджет размера сборки (T8.06). Запускается после `vite build` (см. `pnpm build`): печатает
 * размеры (gzip) стартового набора файлов и самых больших чанков и завершается с ошибкой, если
 * бюджет превышен. «Стартовый набор» — всё, что `dist/index.html` грузит до первой отрисовки
 * (скрипт, modulepreload и стили); лениво загружаемые страницы в него не входят.
 *
 * Бюджеты намеренно держатся близко к текущим значениям (запас ~10–15 %): рост на десятки
 * килобайт должен быть осознанным решением, а не побочным эффектом новой зависимости.
 */
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { gzipSync } from "node:zlib";

const DIST = fileURLToPath(new URL("../dist", import.meta.url));
const KB = 1024;

/** Бюджеты в килобайтах после gzip. */
const BUDGET = {
  initialJs: 280,
  initialCss: 12,
  anyChunk: 100,
  // Sentry грузится динамически и только при заданном VITE_SENTRY_DSN: на старт не влияет.
  optionalSentry: 180,
};

function gzipKb(file) {
  return gzipSync(readFileSync(join(DIST, file))).length / KB;
}

function initialFiles() {
  const html = readFileSync(join(DIST, "index.html"), "utf8");
  const refs = [...html.matchAll(/(?:src|href)="\/(assets\/[^"]+\.(?:js|css))"/g)];
  return [...new Set(refs.map((match) => match[1]))];
}

const isSentry = (file) => file.includes("vendor-sentry");
const all = readdirSync(join(DIST, "assets"))
  .filter((name) => name.endsWith(".js") || name.endsWith(".css"))
  .map((name) => ({ file: `assets/${name}`, kb: gzipKb(`assets/${name}`) }));
const initial = initialFiles();
const initialJs = initial.filter((file) => file.endsWith(".js"));
const initialCss = initial.filter((file) => file.endsWith(".css"));
const sum = (files) => files.reduce((total, file) => total + gzipKb(file), 0);

const rows = [
  ["Стартовый JS (gzip)", sum(initialJs), BUDGET.initialJs],
  ["Стартовые стили (gzip)", sum(initialCss), BUDGET.initialCss],
  [
    "Самый большой чанк (gzip)",
    Math.max(...all.filter((item) => !isSentry(item.file)).map((item) => item.kb)),
    BUDGET.anyChunk,
  ],
  [
    "Необязательный чанк Sentry (gzip)",
    Math.max(0, ...all.filter((item) => isSentry(item.file)).map((item) => item.kb)),
    BUDGET.optionalSentry,
  ],
];

console.log("\nРазмеры сборки (gzip), КБ:");
for (const file of [...initialJs, ...initialCss]) {
  console.log(`  стартовый  ${gzipKb(file).toFixed(1).padStart(7)}  ${file}`);
}
for (const item of [...all]
  .filter((i) => !isSentry(i.file))
  .sort((a, b) => b.kb - a.kb)
  .slice(0, 5)) {
  console.log(`  крупнейший ${item.kb.toFixed(1).padStart(7)}  ${item.file}`);
}
let failed = false;
console.log("\nБюджет:");
for (const [name, value, limit] of rows) {
  const ok = value <= limit;
  failed ||= !ok;
  console.log(`  ${ok ? "ок    " : "ПРЕВЫШЕН"} ${name}: ${value.toFixed(1)} из ${limit} КБ`);
}
// страховка от пустого результата (например, изменился формат index.html)
if (initialJs.length === 0) {
  console.error("В index.html не найден ни один скрипт: проверьте формат сборки");
  failed = true;
}
process.exit(failed ? 1 : 0);
