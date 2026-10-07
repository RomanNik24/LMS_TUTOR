/**
 * Сервер MSW для Node (jsdom). Хэндлеры конкретного теста добавляются через `server.use(...)`;
 * здесь — только общие ответы, которые нужны почти всем экранам (справочник предметов).
 */
import { HttpResponse, http } from "msw";
import { setupServer } from "msw/node";

/** Справочник предметов, как его отдаёт `GET /api/v1/reference/subjects` после сида. */
export const SUBJECTS = [
  { code: "informatics", name: "Информатика" },
  { code: "math", name: "Математика" },
];

export const server = setupServer(
  http.get("*/api/v1/reference/subjects", () => HttpResponse.json(SUBJECTS)),
);
