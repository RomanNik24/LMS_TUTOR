import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { texts } from "@/lib/texts";

import type { ReportPeriod } from "./api";

const t = texts.student.reports;

const PERIODS: ReportPeriod[] = ["weeks4", "months3", "all"];

type PeriodTabsProps = {
  value: ReportPeriod;
  onChange: (period: ReportPeriod) => void;
};

/** Переключатель периода отчёта: 4 недели / 3 месяца / всё (docs/07 §9.1.6). */
export function PeriodTabs({ value, onChange }: PeriodTabsProps) {
  return (
    <Tabs
      value={value}
      onValueChange={(next) => {
        const period = PERIODS.find((item) => item === next);
        if (period !== undefined) onChange(period);
      }}
    >
      <TabsList aria-label={t.periodLabel}>
        {PERIODS.map((period) => (
          <TabsTrigger key={period} value={period}>
            {t.periods[period]}
          </TabsTrigger>
        ))}
      </TabsList>
    </Tabs>
  );
}
