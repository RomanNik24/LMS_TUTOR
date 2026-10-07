import type { HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

/** Карточка по docs/07 §6.4: фон card, радиус 12, граница, тень, отступ 16. */
export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "rounded-md border border-border bg-card p-4 text-card-foreground shadow-card",
        className,
      )}
      {...props}
    />
  );
}
