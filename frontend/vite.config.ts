import { fileURLToPath } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
// defineConfig из vitest/config типизирует секцию test (иначе tsc не знает поле `test`).
import { defineConfig } from "vitest/config";

// Единая конфигурация для Vite и Vitest (Vitest читает этот же файл).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    // Алиас @/ → src/ (docs/12 §2.4): в коде никаких ../../../
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  build: {
    rollupOptions: {
      output: {
        // Библиотеки редко меняются, код приложения — часто: разные файлы кешируются отдельно, и
        // после обновления приложения браузер не скачивает React и остальное заново (Rolldown).
        manualChunks(rawId: string) {
          // Разделитель путей зависит от ОС: приводим к «/», чтобы проверки работали везде.
          const id = rawId.replaceAll("\\", "/");
          if (!id.includes("/node_modules/")) return undefined;
          const inPackage = (...names: string[]) =>
            names.some((name) => id.includes(`/node_modules/${name}/`));
          if (inPackage("react", "react-dom", "react-router", "react-router-dom", "scheduler")) {
            return "vendor-react";
          }
          if (inPackage("zod", "react-hook-form", "@hookform/resolvers")) return "vendor-forms";
          if (inPackage("date-fns", "@date-fns/tz")) return "vendor-date";
          if (id.includes("/node_modules/@telegram-apps/")) return "vendor-telegram";
          return "vendor";
        },
      },
    },
  },
  server: {
    // Туннель для Mini App (scripts/dev_tunnel.*): Vite иначе блокирует незнакомые хосты
    allowedHosts: [".trycloudflare.com"],
    proxy: {
      // В dev запросы /api идут на локальный бэкенд — CORS не нужен (docs/12 §2.3)
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        // X-Forwarded-For: backend считает лимиты по реальному IP клиента, а не по 127.0.0.1
        xfwd: true,
      },
    },
  },
  test: {
    environment: "jsdom",
    // Глобальные expect/it/describe включены: тесты пишутся без импортов vitest
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
