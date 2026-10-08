/**
 * Отдельный процесс с подставным Telegram Bot API. Запускается ДО стека E2E (приложению нужен
 * Telegram при старте): `node e2e/telegram-mock-server.ts` (Node 22.18+ запускает TypeScript сам).
 * Тесты читают отправленные сообщения по `GET /__sent`. Останавливается Ctrl+C.
 */
import { E2E } from "./support/config.ts";
import { TelegramMock } from "./support/telegramMock.ts";

const mock = new TelegramMock();
await mock.start(E2E.telegramMockPort);
process.stdout.write(`Подставной Telegram API: http://0.0.0.0:${String(E2E.telegramMockPort)}\n`);

process.on("SIGINT", () => {
  void mock.stop().then(() => process.exit(0));
});
