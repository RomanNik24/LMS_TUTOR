import { Plus } from "lucide-react";
import { useState } from "react";

import { errorMessage } from "@/api/errors";
import { ErrorState } from "@/components/common/ErrorState";
import { PageSkeleton } from "@/components/common/PageSkeleton";
import { Button } from "@/components/ui/button";
import { useMe } from "@/features/auth/api";
import { MockExamFormDialog } from "@/features/exams/MockExamFormDialog";
import { DEFAULT_TIMEZONE } from "@/features/students/studentForm";
import { todayKey } from "@/lib/datetime";
import { texts } from "@/lib/texts";

import { useAdminStudentReport } from "./api";
import type { ReportPeriod } from "./api";
import { PeriodTabs } from "./PeriodTabs";
import { ReportCharts } from "./ReportCharts";

type StudentProgressTabProps = {
  studentId: number;
  /** Архивному ученику новый результат ввести нельзя. */
  canAddResult: boolean;
};

/** Вкладка «Пробники и прогресс» карточки ученика (docs/07 §9.2.3): графики и ввод пробника. */
export function StudentProgressTab({ studentId, canAddResult }: StudentProgressTabProps) {
  const { data: me } = useMe();
  const timeZone = me?.timezone ?? DEFAULT_TIMEZONE;
  const [period, setPeriod] = useState<ReportPeriod>("months3");
  const [adding, setAdding] = useState(false);
  const query = useAdminStudentReport(studentId, period, timeZone);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <PeriodTabs value={period} onChange={setPeriod} />
        {canAddResult && (
          <Button
            size="compact"
            variant="outline"
            onClick={() => {
              setAdding(true);
            }}
          >
            <Plus className="size-5" aria-hidden />
            {texts.admin.exams.newResult}
          </Button>
        )}
      </div>
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
      {adding && (
        <MockExamFormDialog
          open
          onOpenChange={setAdding}
          defaultDate={todayKey(timeZone)}
          studentId={studentId}
        />
      )}
    </div>
  );
}
