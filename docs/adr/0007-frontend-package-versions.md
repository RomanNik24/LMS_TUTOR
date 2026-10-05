# 0007. Версии пакетов фронтенда (T0.11)

- **Статус:** Принято
- **Дата:** 2026-10-05
- **Контекст:** задача T0.11 (`docs/PLAN_FROM_SCRATCH.md`): каркас `frontend/` на Vite + React + TypeScript, pnpm, строгий режим. По правилам проекта агент обязан выбрать актуальные стабильные и совместимые версии и зафиксировать их в ADR. Нумерация: 0001–0006 зарезервированы за ADR задачи T0.04 (создание `docs/adr/`); этот файл — следующий по счёту.
- **Решение:**

| Пакет | Версия | Причина |
|---|---|---|
| node | 22.13.0 (`.nvmrc`) | Коридор `^20.19 \|\| ^22.13 \|\| >=24` удовлетворяют все выбранные пакеты (Vite 7, Vitest 4, MSW 2). |
| pnpm | 10.19.0 (`packageManager`) | Актуальный стабильный; postinstall для esbuild/MSW разрешён через `pnpm-workspace.yaml`. |
| vite / @vitejs/plugin-react | 7.3.6 / 5.2.0 | Стабильная линейка Vite 7; плагин react 5 совместим с Vite 7 и React 19. |
| react / react-dom / @types/* | 19.2.8 / 19.2.18 / 19.2.3 | Актуальная стабильная ветка React 19. |
| typescript | 5.9.3 | Фиксируем на 5.x (не latest 7.x): typescript-eslint 8 и openapi-typescript 7 рассчитаны на TS 5.x API; strict + noUncheckedIndexedAccess поддерживаются полностью. |
| eslint / @eslint/js / typescript-eslint | 9.39.5 / 9.39.5 / 8.59.4 | ESLint 9 flat config; typescript-eslint 8.59 поддерживает ESLint 9 и TS 5.9. |
| eslint-plugin-react-hooks / eslint-config-prettier / globals | 7.1.1 / 10.1.8 / 16.5.0 | Стабильные версии, совместимые с flat config. |
| tailwindcss / @tailwindcss/vite | 4.2.4 | Tailwind v4 подключается плагином Vite без отдельного PostCSS-конфига; `@theme inline` сопоставляет токены из `docs/07_design.md` §3.4. |
| date-fns / @date-fns/tz | 4.4.0 / 1.4.1 | **Совместимость проверена:** `@date-fns/tz` 1.x объявляет peer `date-fns`: `^3 \|\| ^4`; 1.4.1 — актуальная версия под date-fns 4.4.0. Класс `TZDate` из tz корректно работает с `format` из date-fns 4. |
| openapi-typescript / openapi-fetch | 7.13.0 / 0.17.0 | **Совместимость проверена:** openapi-typescript 7 генерирует интерфейс `paths`, который openapi-fetch 0.x потребляет через `client<schema>`; библиотеки обновляются синхронно. В T0.11 установлены заранее для `gen:api` (реализация — T1.12). |
| vitest | 4.1.11 | Читает секцию `test` из `vite.config.ts`; требует Node из коридора выше. |
| @testing-library/react / jest-dom / jsdom | 16.3.3 / 6.9.1 / 26.1.0 | TL React 16 официально поддерживает React 19. |
| msw | 2.15.0 | `setupServer` для Node-тестов; браузерный worker не нужен до реальных запросов. |
| @fontsource-variable/{unbounded,montserrat,inter} | 5.3.0 | Самохостинг шрифтов без CDN (`docs/07_design.md` §4.1). Variable-пакеты дают веса Unbounded 700–800, Montserrat 700–900 (лого), Inter 400–600 одним подключением `wght.css` с `unicode-range`: браузер грузит подмножества cyrillic/latin по требованию. |

- **Последствия:** версии зафиксированы точечно (без диапазонов), обновление — отдельными осознанными коммитами; при конфликте с новой задачей — новый ADR. Скрипт `telegram-web-app.js` и Telegram SDK намеренно не установлены: интеграция изолирована в `lib/telegram.ts`, подключение SDK — по мере необходимости в T1.x (`docs/12_frontend_guide.md` §5.2).
