import { errorMessage } from "@/api/errors";
import { ErrorState } from "@/components/common/ErrorState";
import { PageSkeleton } from "@/components/common/PageSkeleton";
import { Card } from "@/components/ui/card";
import { useMe } from "@/features/auth/api";
import { DEFAULT_TIMEZONE } from "@/features/students/studentForm";
import { texts } from "@/lib/texts";

import { periodRange, useEarnings } from "./api";

const t = texts.admin.finance.studentTab;
const money = texts.admin.finance.money;
const NO_CUSTOM = { from: "", to: "" } as const;

type StudentFinanceTabProps = {
  studentId: number;
};

/** Вкладка «Финансы» карточки ученика (только владелец): заработок и ожидаемое за месяц. */
export function StudentFinanceTab({ studentId }: StudentFinanceTabProps) {
  const { data: me } = useMe();
  const range = periodRange("month", NO_CUSTOM, me?.timezone ?? DEFAULT_TIMEZONE);
  const query = useEarnings(range, "student");

  if (query.isPending) return <PageSkeleton cards={1} />;
  if (query.isError) {
    return (
      <ErrorState
        message={errorMessage(query.error)}
        onRetry={() => {
          void query.refetch();
        }}
      />
    );
  }
  const row = query.data.rows.find((item) => item.key === String(studentId));
  return (
    <Card className="flex flex-col gap-2">
      <h2 className="text-lg font-bold font-heading">{t.title}</h2>
      {row === undefined ? (
        <p className="text-sm text-muted-foreground font-body">{t.none}</p>
      ) : (
        <dl className="flex flex-col gap-1 font-body">
          <div className="flex justify-between gap-4">
            <dt className="text-muted-foreground">{t.earned}</dt>
            <dd className="font-semibold">{money(row.earned)}</dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt className="text-muted-foreground">{t.expected}</dt>
            <dd className="font-semibold">{money(row.expected)}</dd>
          </div>
          <p className="text-sm text-muted-foreground">{t.lessons(row.earned_lessons)}</p>
        </dl>
      )}
    </Card>
  );
}
