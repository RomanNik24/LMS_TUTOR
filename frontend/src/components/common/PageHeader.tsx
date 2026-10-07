import type { ReactNode } from "react";

type PageHeaderProps = {
  title: string;
  description?: string;
  /** Главные действия страницы (справа на десктопе). */
  actions?: ReactNode;
};

/** Заголовок страницы: H1 Unbounded заглавными и действия справа (docs/07 §4, §7.2). */
export function PageHeader({ title, description, actions }: PageHeaderProps) {
  return (
    <header className="flex flex-wrap items-start justify-between gap-3">
      <div className="flex min-w-0 flex-col gap-1">
        <h1 className="text-xl font-extrabold uppercase tracking-tight text-foreground font-display md:text-2xl">
          {title}
        </h1>
        {description !== undefined && (
          <p className="text-sm text-muted-foreground font-body">{description}</p>
        )}
      </div>
      {actions !== undefined && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </header>
  );
}
