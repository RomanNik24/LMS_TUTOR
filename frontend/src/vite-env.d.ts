/// <reference types="vite/client" />

// Публичные переменные окружения фронтенда (docs/02 §7). Секретов здесь нет и быть не может.
interface ImportMetaEnv {
  /** Username бота без @ — для кнопки «Открыть бота» на экране входа. */
  readonly VITE_BOT_USERNAME?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
