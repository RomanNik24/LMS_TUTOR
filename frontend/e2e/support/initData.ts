import { createHmac } from "node:crypto";

/**
 * Подписанная строка `initData`, как её отдаёт Telegram Mini App (docs/09 §2.2). Подпись считается
 * тестовым токеном стека, поэтому бэкенд принимает её как настоящую и ничего не подменяется.
 */
export function signInitData(botToken: string, user: { id: number; first_name: string }): string {
  const fields: Record<string, string> = {
    auth_date: String(Math.floor(Date.now() / 1000)),
    query_id: "E2E",
    user: JSON.stringify({ id: user.id, first_name: user.first_name, language_code: "ru" }),
  };
  const checkString = Object.keys(fields)
    .sort()
    .map((key) => `${key}=${fields[key] ?? ""}`)
    .join("\n");
  const secret = createHmac("sha256", "WebAppData").update(botToken).digest();
  const hash = createHmac("sha256", secret).update(checkString).digest("hex");
  return new URLSearchParams({ ...fields, hash }).toString();
}

/** Адрес запуска Mini App: initData в хэше, как у Telegram (`tgWebAppData`). */
export function launchUrl(baseUrl: string, path: string, initData: string): string {
  const params = new URLSearchParams({
    tgWebAppData: initData,
    tgWebAppVersion: "8.0",
    tgWebAppPlatform: "tdesktop",
  });
  return `${baseUrl}${path}#${params.toString()}`;
}
