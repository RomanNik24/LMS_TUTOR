// Генерация типов API: OpenAPI бэкенда -> src/api/schema.d.ts (T1.12, docs/03 §14).
//
// 1) uv run python scripts/export_openapi.py <временный файл> (в корне репозитория);
// 2) openapi-typescript <временный файл> -o src/api/schema.d.ts.
// Работает одинаково на Windows, macOS и Linux (без shell-команд rm/cp).
// Сгенерированный файл коммитится и не правится вручную.

import { spawnSync } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const frontendDir = resolve(fileURLToPath(new URL("..", import.meta.url)));
const repoRoot = resolve(frontendDir, "..");
const output = join(frontendDir, "src", "api", "schema.d.ts");

function run(command, args, cwd) {
  const result = spawnSync(command, args, {
    cwd,
    stdio: "inherit",
    shell: process.platform === "win32",
  });
  if (result.error || result.status !== 0) {
    console.error(`Команда не выполнена: ${command} ${args.join(" ")}`);
    process.exit(result.status ?? 1);
  }
}

const workDir = mkdtempSync(join(tmpdir(), "lms-openapi-"));
const specPath = join(workDir, "openapi.json");
try {
  run("uv", ["run", "python", "scripts/export_openapi.py", specPath], repoRoot);
  run("pnpm", ["exec", "openapi-typescript", specPath, "-o", output], frontendDir);
} finally {
  rmSync(workDir, { recursive: true, force: true });
}
console.log(`Типы API записаны: ${output}`);
