import { QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { RouterProvider } from "react-router-dom";

import { createQueryClient } from "@/api/queryClient";
import { applyTelegramTheme } from "@/lib/telegram";
import { createAppRouter } from "@/router";

/**
 * Корень приложения: провайдеры и роутер. Тему (Telegram или prefers-color-scheme)
 * применяем до первой отрисовки (docs/07 §3.5).
 */
applyTelegramTheme();

export function App() {
  // Клиент запросов и роутер создаются один раз на жизнь приложения
  const [queryClient] = useState(createQueryClient);
  const [router] = useState(createAppRouter);
  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  );
}
