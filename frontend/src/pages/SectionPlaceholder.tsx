import type { LucideIcon } from "lucide-react";

import { EmptyState } from "@/components/common/EmptyState";
import { PageHeader } from "@/components/common/PageHeader";

type SectionPlaceholderProps = {
  title: string;
  text: string;
  icon: LucideIcon;
};

/**
 * Пустой раздел до появления его данных (docs/07 §6.16): заголовок и состояние «пусто».
 * Реальные экраны заменят его по этапам плана (расписание — этап 3, ДЗ — этап 4 и т. д.).
 */
export function SectionPlaceholder({ title, text, icon }: SectionPlaceholderProps) {
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={title} />
      <EmptyState icon={icon} title={title} description={text} />
    </div>
  );
}
