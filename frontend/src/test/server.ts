/**
 * Сервер MSW для Node (jsdom). Хэндлеры добавляются по мере появления API
 * (T1.x); пока список пуст — каркас настроен и готов к использованию.
 */
import { setupServer } from "msw/node";

export const server = setupServer();
