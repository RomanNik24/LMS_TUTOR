import { useState } from "react";

import { errorMessage } from "@/api/errors";
import { ErrorState } from "@/components/common/ErrorState";
import { PageHeader } from "@/components/common/PageHeader";
import { PageSkeleton } from "@/components/common/PageSkeleton";
import { useMe } from "@/features/auth/api";
import { DEFAULT_TIMEZONE } from "@/features/students/studentForm";
import { texts } from "@/lib/texts";

import { useMyReport } from "./api";
import type { ReportPeriod } from "./api";
import { PeriodTabs } from "./PeriodTabs";
import { ReportCharts } from "./ReportCharts";

/** «Отчёты» ученика (docs/07 §9.1.6): графики за выбранный период, только свои данные. */
export function StudentReportsPage() {
  const { data: me } = useMe();
  const [period, setPeriod] = useState<ReportPeriod>("weeks4");
  const query = useMyReport(period, me?.timezone ?? DEFAULT_TIMEZONE);

  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={texts.nav.student.reports} />
      <PeriodTabs value={period} onChange={setPeriod} />
      {query.isPending && <PageSkeleton cards={3} />}
      {query.isError && (
        <ErrorState
          message={errorMessage(query.error)}
          onRetry={() => {
            void query.refetch();
          }}
        />
      )}
      {query.data !== undefined && <ReportCharts report={query.data} />}
    </div>
  );
}
