import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { initSentry } from "./lib/sentry";
import { initTelegram } from "./lib/telegram";
import "./styles/globals.css";

// SDK Telegram инициализируется один раз до отрисовки; вне Telegram — ничего не делает.
initTelegram();
void initSentry(import.meta.env.VITE_SENTRY_DSN);

// Точка входа SPA (docs/12 §3): провайдеры и роутер подключены в App.
const rootElement = document.getElementById("root");
if (rootElement === null) {
  throw new Error("В index.html нет элемента #root");
}

createRoot(rootElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
