import { Skeleton } from "@/components/ui/skeleton";
import { texts } from "@/lib/texts";

type PageSkeletonProps = {
  /** Сколько карточек-скелетонов показать. */
  cards?: number;
};

/** Скелетон страницы: заголовок и несколько карточек (docs/07 §6.16). */
export function PageSkeleton({ cards = 3 }: PageSkeletonProps) {
  return (
    <div className="flex flex-col gap-4" role="status" aria-label={texts.common.loading}>
      <Skeleton className="h-8 w-2/3" />
      {Array.from({ length: cards }, (_, index) => (
        <Skeleton key={index} className="h-24 w-full" />
      ))}
    </div>
  );
}
