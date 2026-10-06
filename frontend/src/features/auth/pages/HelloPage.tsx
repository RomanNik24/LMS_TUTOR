import { texts } from "@/lib/texts";

import { useMe } from "../api";

/** Страница после входа: «Привет, {имя}» и роль (T1.13). Маршрутами по ролям займутся позже. */
export function HelloPage() {
  const { data: me } = useMe();
  if (me === undefined) {
    return null;
  }
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-3 bg-background px-4">
      <h1 className="text-2xl font-extrabold uppercase tracking-tight text-primary font-display md:text-3xl">
        {texts.hello.greeting.replace("{name}", me.display_name)}
      </h1>
      <p className="text-sm text-muted-foreground font-body">
        {texts.hello.roleLabel}: {texts.roles[me.role]}
      </p>
    </main>
  );
}
