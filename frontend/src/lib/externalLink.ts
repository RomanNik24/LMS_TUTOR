/**
 * Внешние ссылки (docs/09 §1, T8.06): только `https://` (для локальной разработки допустим
 * `http://localhost` и `127.0.0.1`), всегда в новой вкладке (`rel` с noopener и noreferrer).
 * Адреса приходят из данных (Телемост, доска, подписанные ссылки), поэтому схему проверяем здесь:
 * `javascript:` и другие схемы превращаются в неактивную ссылку.
 */
const LOCAL_HOSTS = new Set(["localhost", "127.0.0.1", "[::1]"]);

export function isSafeExternalUrl(value: string): boolean {
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    return false;
  }
  if (url.protocol === "https:") return true;
  return url.protocol === "http:" && LOCAL_HOSTS.has(url.hostname);
}

/** Атрибуты для `<a>`: у небезопасного адреса `href` не выставляется. */
export function externalLinkProps(value: string) {
  return {
    href: isSafeExternalUrl(value) ? value : undefined,
    target: "_blank",
    rel: "noopener noreferrer",
  } as const;
}
