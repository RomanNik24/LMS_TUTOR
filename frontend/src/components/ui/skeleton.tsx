import type { HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

/** Скелетон загрузки: серая подложка с мягким мерцанием (docs/07 §6.16); с reduced-motion без анимации. */
export function Skeleton({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      aria-hidden
      className={cn("animate-pulse rounded-md bg-gray-200 motion-reduce:animate-none", className)}
      {...props}
    />
  );
}
