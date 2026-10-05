/**
 * Настройка окружения тестов (Vitest + Testing Library + MSW).
 * Подключается через setupFiles в vite.config.ts.
 */
import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll } from "vitest";

import { server } from "./server";

// jsdom не реализует matchMedia; заглушка нужна lib/telegram.ts (вне Telegram он
// спрашивает prefers-color-scheme). Возвращаем «светлая тема» — как основной режим брендбука.
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string): MediaQueryList =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => undefined,
      removeListener: () => undefined,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      dispatchEvent: () => false,
    }) satisfies MediaQueryList,
});

// MSW: все сетевые запросы в тестах идут через mock-сервер, реальный бэкенд не нужен.
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  cleanup();
  server.resetHandlers();
});
afterAll(() => server.close());
