/**
 * Настройка окружения тестов (Vitest + Testing Library + MSW).
 * Подключается через setupFiles в vite.config.ts.
 */
import "@testing-library/jest-dom/vitest";

import { cleanup, configure } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, beforeEach } from "vitest";

import { server } from "./server";
import { setViewport } from "./viewport";

const MOBILE_WIDTH = 360;

// Страницы админки грузятся лениво (React.lazy): при первом обращении Vitest трансформирует модуль
// на лету, и на нагруженном ПК это дольше стандартной секунды ожидания findBy*/waitFor.
// Увеличиваем только предел ожидания; проверки остаются прежними (аудит 2026-10-08, п. 8).
configure({ asyncUtilTimeout: 5000 });

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
