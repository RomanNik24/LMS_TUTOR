import { applyTelegramTheme } from "@/lib/telegram";
import { HomePage } from "@/pages/HomePage";

/**
 * Корень приложения. Роутер появляется в T1.x; пока одна реальная страница (T0.11).
 * Тему (Telegram или prefers-color-scheme) применяем до первой отрисовки (docs/07 §3.5).
 */
applyTelegramTheme();

export function App() {
  return <HomePage />;
}
