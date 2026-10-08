import { ClipboardList } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { errorMessage } from "@/api/errors";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { PageHeader } from "@/components/common/PageHeader";
import { PageSkeleton } from "@/components/common/PageSkeleton";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useMe } from "@/features/auth/api";
import { formatDate, formatTime } from "@/lib/datetime";
import { texts } from "@/lib/texts";
import { useSubjectName } from "@/features/reference/api";

import { PAGE_SIZE, useStudentHomework } from "./studentApi";
import type { StudentAssignment, StudentHomeworkFilter } from "./studentApi";

const t = texts.student.homework;

function Row({ item, timeZone }: { item: StudentAssignment; timeZone: string }) {
  const subjectLabel = useSubjectName();
  const status = item.is_overdue ? "homework.overdue" : (`homework.${item.status}` as const);
  return (
    <Link
      to={`/app/homework/${String(item.assignment_id)}`}
      className="block rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <Card className="flex flex-col gap-1 p-4">
        <div className="flex items-start justify-between gap-2">
          <span className="text-base font-bold font-heading">{item.title}</span>
          <StatusBadge status={status} />
        </div>
        <span className="text-sm text-muted-foreground font-body">
          {subjectLabel(item.subject_code)} ·{" "}
          {t.dueAt(`${formatDate(item.due_at, timeZone)}, ${formatTime(item.due_at, timeZone)}`)}
        </span>
        {item.score !== null && (
          <span className="text-sm font-semibold text-success-fg font-body">
            {t.result(item.score, item.max_score, item.score_percent)}
          </span>
        )}
      </Card>
    </Link>
  );
}

function Tab({ filter, timeZone }: { filter: StudentHomeworkFilter; timeZone: string }) {
  const [limit, setLimit] = useState(PAGE_SIZE);
  const query = useStudentHomework(filter, limit);
  if (query.isPending) return <PageSkeleton />;
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
  if (query.data.items.length === 0) {
    return <EmptyState icon={ClipboardList} title={t.empty[filter]} />;
  }
  return (
    <div className="flex flex-col gap-3">
      <ul className="flex flex-col gap-3">
        {query.data.items.map((item) => (
          <li key={item.assignment_id}>
            <Row item={item} timeZone={timeZone} />
          </li>
        ))}
      </ul>
      {query.data.items.length < query.data.total && (
        <Button
          variant="outline"
          onClick={() => {
            setLimit((value) => value + PAGE_SIZE);
          }}
        >
          {t.loadMore}
        </Button>
      )}
    </div>
  );
}

const TABS: { value: StudentHomeworkFilter; label: string }[] = [
  { value: "active", label: t.tabActive },
  { value: "submitted", label: t.tabSubmitted },
  { value: "graded", label: t.tabGraded },
  { value: "expired", label: t.tabExpired },
];

/** Список ДЗ ученика (docs/07 §9.1.4): вкладки по статусу, просроченные сверху с красным бейджем. */
export function StudentHomeworkPage() {
  const { data: me } = useMe();
  const timeZone = me?.timezone ?? "Europe/Moscow";
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t.title} />
      <Tabs defaultValue="active" className="flex flex-col gap-4">
        <TabsList className="w-full overflow-x-auto">
          {TABS.map((tab) => (
            <TabsTrigger key={tab.value} value={tab.value}>
              {tab.label}
            </TabsTrigger>
          ))}
        </TabsList>
        {TABS.map((tab) => (
          <TabsContent key={tab.value} value={tab.value}>
            <Tab filter={tab.value} timeZone={timeZone} />
          </TabsContent>
        ))}
      </Tabs>
    </div>
  );
}
