/**
 * ЕДИНСТВЕННОЕ место в проекте, где разрешено обращаться к Telegram SDK и
 * window.Telegram (docs/06 B3, docs/12 §5.2). Остальной код импортирует только
 * функции этого модуля; ESLint (no-restricted-imports / no-restricted-syntax)
 * запрещает обход этого правила.
 *
 * SDK (@telegram-apps/sdk-react, версии — ADR 0008) используется только здесь:
 * инициализация, нативная кнопка «Назад», тема. Вне Telegram все функции безопасно
 * ничего не делают. Типизированный слой без any: известное поле описываем явно,
 * остальное — unknown (docs/12 §1.4).
 */

import { backButton, init, isTMA, miniApp } from "@telegram-apps/sdk-react";

/** Минимальная часть объекта window.Telegram, которую мы читаем. */
type TelegramWebAppUser = {
  id: number;
  first_name: string;
  last_name?: string;
  username?: string;
};

// theme не описан в официальном типе WebApp, но присутствует в WebView Telegram —
// читаем его только через проверку формы (unknown), без any и без доверия.
type TelegramWebApp = {
  initDataUnsafe?: {
    user?: TelegramWebAppUser;
  };
  theme?: unknown;
};

/** Расширение Window: явного объявления достаточно, касты не нужны. */
declare global {
  interface Window {
    Telegram?: TelegramWebApp;
  }
}

// Читаем параметры запуска Mini App из хэша URL ОДИН РАЗ при загрузке модуля,
// до запуска роутера: навигация может затереть хэш (docs/12 §5.2).
function readInitDataFromHash(): string | null {
  const params = new URLSearchParams(window.location.hash.slice(1));
  return params.get("tgWebAppData"); // URLSearchParams сам декодирует значение
}

const initialInitData: string | null = readInitDataFromHash();

export function getInitData(): string | null {
  return initialInitData;
}

export function isTelegramMiniApp(): boolean {
  return initialInitData !== null && initialInitData.length > 0;
}

/** Имя пользователя из initDataUnsafe (для отладочных экранов); вне Telegram — null. */
export function getTelegramUserName(): string | null {
  return window.Telegram?.initDataUnsafe?.user?.first_name ?? null;
}

/**
 * Тема Telegram → класс .dark на <html> (docs/07 §3.5: режим определяется темой
 * Telegram, в браузере — prefers-color-scheme; переключателя в MVP нет).
 * Возвращает применённую тему, чтобы вызывающий код мог синхронизировать своё состояние.
 */
export function applyTelegramTheme(): "light" | "dark" {
  const theme: "light" | "dark" = resolveColorScheme();
  document.documentElement.classList.toggle("dark", theme === "dark");
  return theme;
}

function readSdkColorScheme(): "light" | "dark" | null {
  try {
    if (miniApp.isMounted()) {
      return miniApp.isDark() ? "dark" : "light";
    }
  } catch {
    // SDK недоступен — берём следующий источник темы
  }
  return null;
}

function resolveColorScheme(): "light" | "dark" {
  // 1) SDK (после initTelegram); 2) theme из window.Telegram — через проверку формы
  // (unknown → конкретный тип), без any; 3) prefers-color-scheme браузера.
  const sdkScheme = readSdkColorScheme();
  if (sdkScheme !== null) {
    return sdkScheme;
  }
  const scheme = readThemeColorScheme(window.Telegram?.theme);
  if (scheme !== null) {
    return scheme;
  }
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function readThemeColorScheme(theme: unknown): "light" | "dark" | null {
  if (typeof theme !== "object" || theme === null) {
    return null;
  }
  // Partial<Record<string, unknown>> — безопасный способ прочитать поле неизвестного объекта.
  const themeRecord: Partial<Record<string, unknown>> = theme;
  const colorScheme = themeRecord["colorScheme"];
  if (colorScheme === "light" || colorScheme === "dark") {
    return colorScheme;
  }
  return null;
}

/**
 * Инициализация SDK при запуске внутри Telegram (вызывается один раз в main.tsx
 * до отрисовки). Вне Telegram и при любой ошибке SDK приложение продолжает работать.
 * Возвращает true, если SDK инициализирован.
 */
export function initTelegram(): boolean {
  if (!isTelegramMiniApp() || !isTMA()) {
    return false;
  }
  try {
    init();
    if (miniApp.mountSync.isAvailable()) {
      miniApp.mountSync();
    }
    if (miniApp.ready.isAvailable()) {
      miniApp.ready();
    }
    return true;
  } catch {
    return false;
  }
}

/**
 * Показать нативную кнопку «Назад» Telegram и вызвать onBack при нажатии
 * (docs/12 §5.5). Возвращает функцию отписки: прячет кнопку и снимает обработчик.
 * Вне Telegram — ничего не делает.
 */
export function showBackButton(onBack: () => void): () => void {
  try {
    if (!backButton.isSupported()) {
      return () => undefined;
    }
    if (!backButton.isMounted()) {
      backButton.mount();
    }
    backButton.show();
    const offClick = backButton.onClick(onBack);
    return () => {
      offClick();
      backButton.hide();
    };
  } catch {
    return () => undefined;
  }
}
