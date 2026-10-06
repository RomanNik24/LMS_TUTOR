// ESLint flat config (docs/T0.11 п.5)
import js from "@eslint/js";
import prettierConfig from "eslint-config-prettier";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist/**", "node_modules/**", "coverage/**", "src/api/schema.d.ts"] },
  js.configs.recommended,
  ...tseslint.configs.recommendedTypeChecked,
  {
    /* Конфигурационные JS/MJS-файлы не проходят через TS-парсер: отключаем типизированные правила */
    files: ["**/*.{js,mjs,cjs}"],
    extends: [tseslint.configs.disableTypeChecked],
  },
  {
    /* Node-скрипты (scripts/*.mjs) выполняются в Node, а не в браузере */
    files: ["scripts/**/*.mjs"],
    languageOptions: { globals: { ...globals.node } },
  },
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      globals: { ...globals.browser },
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    plugins: {
      // Плагин хуков React (docs/02 §3.2)
      "react-hooks": reactHooks,
    },
    rules: {
      /* Запрет any: вместо него unknown + проверки (docs/06 B1) */
      "@typescript-eslint/no-explicit-any": "error",
      "@typescript-eslint/no-unsafe-assignment": "error",
      "@typescript-eslint/no-unsafe-member-access": "error",
      "@typescript-eslint/no-unsafe-call": "error",
      "@typescript-eslint/no-unsafe-return": "error",
      "@typescript-eslint/no-unsafe-argument": "error",

      /* Запрет ts-ignore / ts-nocheck (docs/06 B1) */
      "@typescript-eslint/ban-ts-comment": "error",

      /* React hooks */
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "error",

      /* dangerouslySetInnerHTML запрещён (docs/06 B5, docs/12 §12): прямой вызов — без плагина */
      "no-restricted-properties": [
        "error",
        {
          object: "*",
          property: "dangerouslySetInnerHTML",
          message: "dangerouslySetInnerHTML запрещён (docs/06 B5). React экранирует JSX сам.",
        },
      ],

      /* Telegram SDK и window.Telegram — только в src/lib/telegram.ts (docs/06 B3) */
      "no-restricted-imports": [
        "error",
        {
          paths: [
            {
              name: "@telegram-apps/sdk-react",
              message: "Интеграция с Telegram изолирована в src/lib/telegram.ts (docs/06 B3).",
            },
            {
              name: "@telegram-apps/sdk",
              message: "Интеграция с Telegram изолирована в src/lib/telegram.ts (docs/06 B3).",
            },
          ],
          patterns: [
            {
              group: ["@telegram-apps/*"],
              message: "Интеграция с Telegram изолирована в src/lib/telegram.ts (docs/06 B3).",
            },
          ],
        },
      ],
      "no-restricted-syntax": [
        "error",
        {
          selector:
            "MemberExpression[object.property.name='Telegram'], MemberExpression > Identifier[name='Telegram']",
          message: "Доступ к window.Telegram разрешён только в src/lib/telegram.ts (docs/06 B3).",
        },
      ],
    },
  },
  {
    /* telegram.ts — единственное место, где разрешён Telegram SDK/window.Telegram */
    files: ["src/lib/telegram.ts"],
    rules: {
      "no-restricted-imports": "off",
      "no-restricted-syntax": "off",
    },
  },
  {
    /* Тестовое окружение: глобалы Vitest (describe/it/expect включены через globals: true) */
    files: ["src/test/**", "**/*.test.{ts,tsx}"],
    languageOptions: {
      globals: { ...globals.browser, ...globals.node },
    },
  },
  prettierConfig,
);
