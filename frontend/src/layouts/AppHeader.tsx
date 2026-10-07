import { useMe } from "@/features/auth/api";
import { texts } from "@/lib/texts";
import { initials } from "@/lib/utils";

/** Шапка Student App: мелкий логотип слева и круглые инициалы справа (docs/07 §7.1). */
export function AppHeader() {
  const { data: me } = useMe();
  return (
    <header className="flex h-14 items-center justify-between border-b border-border bg-card px-4">
      <span className="text-sm font-extrabold uppercase tracking-tight text-primary font-display">
        {texts.common.brand}
      </span>
      {me !== undefined && (
        <span
          role="img"
          aria-label={`${texts.common.profileAvatar}: ${me.display_name}`}
          className="inline-flex size-9 items-center justify-center rounded-full bg-secondary text-sm font-bold text-secondary-foreground font-heading"
        >
          {initials(me.display_name)}
        </span>
      )}
    </header>
  );
}
