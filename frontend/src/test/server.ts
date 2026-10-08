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

/** Типы экзаменов, как их отдаёт `GET /api/v1/reference/exam-types` после сида. */
export const EXAM_TYPES = [
  {
    id: 1,
    code: "oge_informatics",
    subject_code: "informatics",
    kind: "oge",
    result_kind: "grade_2_5",
    max_primary: 21,
    name: "ОГЭ — Информатика",
    uses_geometry: false,
  },
  {
    id: 2,
    code: "oge_math",
    subject_code: "math",
    kind: "oge",
    result_kind: "grade_2_5",
    max_primary: 31,
    name: "ОГЭ — Математика",
    uses_geometry: true,
  },
  {
    id: 3,
    code: "ege_informatics",
    subject_code: "informatics",
    kind: "ege",
    result_kind: "test_100",
    max_primary: 29,
    name: "ЕГЭ — Информатика",
    uses_geometry: false,
  },
];

export const server = setupServer(
  http.get("*/api/v1/reference/subjects", () => HttpResponse.json(SUBJECTS)),
  http.get("*/api/v1/reference/exam-types", () => HttpResponse.json(EXAM_TYPES)),
);
