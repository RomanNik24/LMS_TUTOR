import { E2E } from "./config";
import type { SentMessage } from "./telegramMock";

/** Тексты, которые бот отправил в чат через подставной Telegram (процесс telegram-mock-server). */
export async function sentTo(chatId: number): Promise<string[]> {
  const response = await fetch(`http://127.0.0.1:${String(E2E.telegramMockPort)}/__sent`);
  const sent = (await response.json()) as SentMessage[];
  return sent.filter((item) => item.chatId === chatId).map((item) => item.text);
}
