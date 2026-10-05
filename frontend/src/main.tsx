import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import "./styles/globals.css";

// Точка входа SPA (docs/12 §3). Провайдеры и роутер подключаются в следующих задачах.
const rootElement = document.getElementById("root");
if (rootElement === null) {
  throw new Error("В index.html нет элемента #root");
}

createRoot(rootElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
