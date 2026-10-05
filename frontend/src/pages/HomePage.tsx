import { texts } from "@/lib/texts";

/**
 * Единственная страница каркаса (T0.11). Оформление — по docs/07:
 * H1 Unbounded заглавными, фон/текст только через токены (bg-background, text-foreground).
 */
export function HomePage() {
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-4 bg-background px-4">
      <h1 className="text-2xl font-extrabold uppercase tracking-tight text-primary font-display md:text-3xl">
        {texts.app.greeting}
      </h1>
      <p className="text-sm text-muted-foreground font-body">{texts.app.title}</p>
    </main>
  );
}
