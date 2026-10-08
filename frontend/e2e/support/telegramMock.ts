import { createServer } from "node:http";
import type { IncomingMessage, Server } from "node:http";

/** Сообщение, которое бот попытался отправить через Bot API. */
export type SentMessage = { chatId: number; text: string };

/**
 * Подставной Telegram Bot API. Стек запускается с `TELEGRAM_API_BASE` на этот сервер, поэтому
 * уведомления никуда не уходят, а тест видит их тексты. Отвечает так, чтобы aiogram считал вызовы
 * успешными; `getUpdates` отдаёт пустой список после паузы (long polling).
 */
export class TelegramMock {
  readonly sent: SentMessage[] = [];
  private server: Server | null = null;

  async start(port: number): Promise<void> {
    this.server = createServer((request, response) => {
      void this.handle(request).then((body) => {
        response.setHeader("Content-Type", "application/json");
        response.end(JSON.stringify(body));
      });
    });
    await new Promise<void>((resolve) => this.server?.listen(port, "0.0.0.0", resolve));
  }

  async stop(): Promise<void> {
    await new Promise<void>((resolve) => {
      if (this.server === null) resolve();
      else this.server.close(() => resolve());
    });
  }

  /** Тексты, отправленные в чат. */
  textsTo(chatId: number): string[] {
    return this.sent.filter((item) => item.chatId === chatId).map((item) => item.text);
  }

  private async handle(request: IncomingMessage): Promise<unknown> {
    const method = (request.url ?? "").split("/").pop()?.split("?")[0] ?? "";
    const raw = await new Promise<string>((resolve) => {
      let data = "";
      request.on("data", (chunk: Buffer) => (data += chunk.toString()));
      request.on("end", () => resolve(data));
    });
    const payload = parseBody(raw, request.headers["content-type"]);
    switch (method) {
      case "getMe":
        return {
          ok: true,
          result: { id: 100000, is_bot: true, first_name: "E2E", username: "e2e_bot" },
        };
      case "getUpdates":
        await new Promise((resolve) => setTimeout(resolve, 1000));
        return { ok: true, result: [] };
      case "sendMessage": {
        const chatId = Number(payload["chat_id"]);
        const rawText = payload["text"];
        const text = typeof rawText === "string" ? rawText : "";
        this.sent.push({ chatId, text });
        return {
          ok: true,
          result: {
            message_id: this.sent.length,
            date: Math.floor(Date.now() / 1000),
            chat: { id: chatId, type: "private" },
            text,
          },
        };
      }
      default:
        return { ok: true, result: true };
    }
  }
}

function parseBody(raw: string, contentType: string | undefined): Record<string, unknown> {
  try {
    if (contentType?.includes("application/json")) {
      return JSON.parse(raw) as Record<string, unknown>;
    }
    const boundary = /boundary=(?:"([^"]+)"|([^;]+))/.exec(contentType ?? "");
    if (boundary !== null) return parseMultipart(raw, boundary[1] ?? boundary[2] ?? "");
    return Object.fromEntries(new URLSearchParams(raw));
  } catch {
    return {};
  }
}

/** Поля формы `multipart/form-data` (так aiogram отправляет вызовы Bot API). */
function parseMultipart(raw: string, boundary: string): Record<string, unknown> {
  const fields: Record<string, unknown> = {};
  for (const part of raw.split(`--${boundary}`)) {
    const match = /name="([^"]+)"\r\n\r\n([\s\S]*?)\r\n$/.exec(part);
    if (match?.[1] !== undefined) fields[match[1]] = match[2];
  }
  return fields;
}
