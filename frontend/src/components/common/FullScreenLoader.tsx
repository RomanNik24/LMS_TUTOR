import { texts } from "@/lib/texts";

/** Лоадер на весь экран (проверка входа, автовход). */
export function FullScreenLoader() {
  return (
    <main
      className="flex min-h-dvh items-center justify-center bg-background px-4"
      role="status"
      aria-live="polite"
    >
      <p className="text-sm text-muted-foreground font-body">{texts.common.loading}</p>
    </main>
  );
}
