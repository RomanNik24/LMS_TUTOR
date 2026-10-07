import { texts } from "@/lib/texts";
import { cn } from "@/lib/utils";

/**
 * Единый статус-бейдж (docs/07 §6.6): ЕДИНСТВЕННАЯ таблица соответствия «статус → вид».
 * Тексты — в texts.status, другие места таблицу не дублируют.
 */
type Variant = "brand" | "success" | "successTint" | "neutral" | "warning" | "danger" | "dark";

const VARIANT_CLASSES: Record<Variant, string> = {
  brand: "bg-secondary text-secondary-foreground",
  success: "bg-primary text-primary-foreground",
  successTint: "bg-success-bg text-success-fg",
  neutral: "bg-muted text-ink",
  warning: "bg-warning-bg text-warning-fg",
  danger: "bg-danger-bg text-danger-fg",
  dark: "bg-ink text-brand-white",
};

export const STATUS_VARIANTS = {
  "lesson.scheduled": "brand",
  "lesson.completed": "success",
  "lesson.cancelled": "neutral",
  "homework.assigned": "neutral",
  "homework.submitted": "brand",
  "homework.needs_revision": "warning",
  "homework.graded": "successTint",
  "homework.expired": "dark",
  "homework.overdue": "danger",
  "attendance.pending": "neutral",
  "attendance.attended": "successTint",
  "attendance.no_show": "danger",
  "attendance.cancelled": "neutral",
  "bot.blocked": "danger",
} as const satisfies Record<keyof typeof texts.status, Variant>;

export type StatusKey = keyof typeof STATUS_VARIANTS;

type StatusBadgeProps = {
  status: StatusKey;
  className?: string;
};

export function StatusBadge({ status, className }: StatusBadgeProps) {
  const variant = STATUS_VARIANTS[status];
  return (
    <span
      data-variant={variant}
      className={cn(
        "inline-flex h-6 items-center gap-1.5 rounded-sm px-2 text-[11px] font-extrabold uppercase tracking-wide font-heading",
        VARIANT_CLASSES[variant],
        className,
      )}
    >
      <span
        aria-hidden
        className={cn("size-1.5 rounded-full bg-current", variant === "warning" && "bg-highlight")}
      />
      {texts.status[status]}
    </span>
  );
}
