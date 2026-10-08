/**
 * Согласованность с CSP (`default-src 'self'; script-src 'self'; style-src 'self'; font-src 'self'`,
 * docs/09 §1, T8.06): в разметке и стилях нет внешних скриптов, шрифтов, картинок и встроенного кода.
 */
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const ROOT = process.cwd();
const html = readFileSync(join(ROOT, "index.html"), "utf8");

function cssFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return cssFiles(path);
    return entry.name.endsWith(".css") ? [path] : [];
  });
}

describe("index.html", () => {
  it("не грузит ничего с внешних адресов", () => {
    expect(html.match(/(?:src|href)=["'](?:https?:)?\/\//g) ?? []).toEqual([]);
  });

  it("без встроенных скриптов и стилей (script-src и style-src только 'self')", () => {
    const inlineScripts = [...html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/g)].filter(
      ([, attrs, body]) => !/\bsrc=/.test(attrs ?? "") || (body ?? "").trim() !== "",
    );
    expect(inlineScripts).toEqual([]);
    expect(html).not.toMatch(/<style\b|\sstyle=|\sonclick=|\sonload=/);
  });
});

describe("стили", () => {
  const files = cssFiles(join(ROOT, "src"));

  it("найдены файлы стилей", () => {
    expect(files.length).toBeGreaterThan(0);
  });

  it.each(files)("%s: без внешних @import, шрифтов и картинок", (file) => {
    const css = readFileSync(file, "utf8");
    expect(css).not.toMatch(/@import\s+(?:url\()?["']?(?:https?:)?\/\//);
    expect(css).not.toMatch(/url\(\s*["']?(?:https?:)?\/\//);
  });
});
