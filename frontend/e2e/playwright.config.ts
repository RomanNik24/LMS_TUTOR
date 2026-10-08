/**
 * Playwright (T8.07): сквозные сценарии на полном стеке. Не входит в `pnpm test` и CI-job frontend:
 * нужен запущенный стек (docker compose --profile full) с тестовым токеном бота и подставным
 * Telegram API. Подробности — README, раздел «Сквозные тесты (E2E)».
 */
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  // Один воркер: сценарии делят одну базу и один подставной Telegram.
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 180_000,
  expect: { timeout: 10_000 },
  reporter: [["list"], ["html", { open: "never", outputFolder: "../e2e-report" }]],
  outputDir: "../e2e-results",
  use: {
    baseURL: process.env["E2E_BASE_URL"] ?? "http://127.0.0.1:18080",
    trace: "retain-on-failure",
    video: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  // E2E_BROWSER_CHANNEL=chrome (или msedge) — взять установленный браузер, если скачать
  // Chromium Playwright нельзя (нет доступа к cdn.playwright.dev).
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        ...(process.env["E2E_BROWSER_CHANNEL"]
          ? { channel: process.env["E2E_BROWSER_CHANNEL"] }
          : {}),
      },
    },
  ],
});
