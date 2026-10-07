import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

type EmptyStateProps = {
  icon: LucideIcon;
  title: string;
  description?: string;
  /** Кнопка действия, если оно уместно. */
  action?: ReactNode;
};

/** Пустое состояние (docs/07 §6.16): одна контурная иконка 40 px, заголовок, подсказка. */
export function EmptyState({ icon: Icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center gap-3 px-4 py-10 text-center" role="status">
      <Icon className="size-10 text-primary" strokeWidth={1.75} aria-hidden />
      <h2 className="text-lg font-bold text-foreground font-heading">{title}</h2>
      {description !== undefined && (
        <p className="max-w-sm text-sm text-muted-foreground font-body">{description}</p>
      )}
      {action}
    </div>
  );
}
