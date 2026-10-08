/** Настройки E2E из окружения. Значения должны совпадать с теми, с которыми запущен стек. */
function required(name: string, fallback?: string): string {
  const value = process.env[name] ?? fallback;
  if (value === undefined || value === "") {
    throw new Error(`E2E: задайте переменную окружения ${name}`);
  }
  return value;
}

export const E2E = {
  baseUrl: process.env["E2E_BASE_URL"] ?? "http://127.0.0.1:18080",
  /** Тестовый токен бота, с которым запущен стек: им подписывается initData. Не настоящий токен. */
  botToken: required("E2E_BOT_TOKEN", "100000:E2E_TEST_TOKEN_NOT_REAL"),
  ownerTelegramId: Number(required("E2E_OWNER_TG_ID", "900000001")),
  studentTelegramId: Number(required("E2E_STUDENT_TG_ID", "900000002")),
  studentName: "E2E Ученик",
  /** Порт подставного Telegram API; стек запускается с TELEGRAM_API_BASE на этот адрес. */
  telegramMockPort: Number(required("E2E_TELEGRAM_MOCK_PORT", "18081")),
  /** Сколько ждать уведомление: рассылка идёт фоновой задачей раз в минуту. */
  notificationTimeoutMs: 150_000,
} as const;
