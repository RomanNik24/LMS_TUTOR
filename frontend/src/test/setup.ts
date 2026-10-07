/**
 * Настройка окружения тестов (Vitest + Testing Library + MSW).
 * Подключается через setupFiles в vite.config.ts.
 */
import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, beforeEach } from "vitest";

import { server } from "./server";
import { setViewport } from "./viewport";

const MOBILE_WIDTH = 360;

// jsdom не реализует matchMedia: подставляем заглушку (мобильная ширина 360 px, светлая тема).
// Тесты лэйаутов меняют ширину через setViewport().
beforeEach(() => {
  setViewport(MOBILE_WIDTH);
});

// MSW: все сетевые запросы в тестах идут через mock-сервер, реальный бэкенд не нужен.
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  cleanup();
  server.resetHandlers();
});
afterAll(() => server.close());
