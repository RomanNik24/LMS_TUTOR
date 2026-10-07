import { ClipboardList, Plus } from "lucide-react";
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
import { formatDate, formatTime, shiftDayKey, todayKey } from "@/lib/datetime";
import { texts } from "@/lib/texts";

import { PAGE_SIZE, useHomeworkList, useReviewQueue } from "./api";
import { HomeworkFormDialog } from "./HomeworkFormDialog";

const t = texts.admin.homework;
const DEFAULT_DUE_DAYS = 7;
const cardLink =
  "block rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

function QueueTab({ timeZone }: { timeZone: string }) {
  const [limit, setLimit] = useState(PAGE_SIZE);
  const query = useReviewQueue(limit);
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
    return <EmptyState icon={ClipboardList} title={t.queueEmpty} />;
  }
  return (
    <div className="flex flex-col gap-3">
      <ul className="flex flex-col gap-3">
        {query.data.items.map((row) => (
          <li key={row.assignment_id}>
            <Link to={`/admin/assignments/${String(row.assignment_id)}`} className={cardLink}>
              <Card className="flex flex-col gap-1 p-4">
                <span className="text-base font-bold font-heading">{row.student_name}</span>
                <span className="text-sm font-body">{row.title}</span>
                {row.submitted_at !== null && (
                  <span className="text-sm text-muted-foreground font-body">
                    {t.submittedAt(
                      `${formatDate(row.submitted_at, timeZone)}, ${formatTime(row.submitted_at, timeZone)}`,
                    )}
                  </span>
                )}
                {row.is_overdue && <StatusBadge status="homework.overdue" />}
              </Card>
            </Link>
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

function HomeworkTab() {
  const [limit, setLimit] = useState(PAGE_SIZE);
  const query = useHomeworkList(limit);
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
    return <EmptyState icon={ClipboardList} title={t.listEmpty} />;
  }
  return (
    <div className="flex flex-col gap-3">
      <ul className="flex flex-col gap-3">
        {query.data.items.map((item) => (
          <li key={item.id}>
            <Link to={`/admin/homework/${String(item.id)}`} className={cardLink}>
              <Card className="flex flex-col gap-1 p-4">
                <span className="text-base font-bold font-heading">{item.title}</span>
                <span className="text-sm text-muted-foreground font-body">
                  {t.submittedOf(item.submitted_count, item.assigned_count)}
                </span>
              </Card>
            </Link>
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

/** Раздел «ДЗ» админки: очередь проверки, список заданий и создание (docs/07 §9.2.8). */
export function AdminHomeworkPage() {
  const { data: me } = useMe();
  const timeZone = me?.timezone ?? "Europe/Moscow";
  const [creating, setCreating] = useState(false);

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title={t.title}
        actions={
          <Button
            size="compact"
            onClick={() => {
              setCreating(true);
            }}
          >
            <Plus className="size-5" aria-hidden />
            {t.newHomework}
          </Button>
        }
      />
      <Tabs defaultValue="queue" className="flex flex-col gap-4">
        <TabsList>
          <TabsTrigger value="queue">{t.tabQueue}</TabsTrigger>
          <TabsTrigger value="homework">{t.tabHomework}</TabsTrigger>
        </TabsList>
        <TabsContent value="queue">
          <QueueTab timeZone={timeZone} />
        </TabsContent>
        <TabsContent value="homework">
          <HomeworkTab />
        </TabsContent>
      </Tabs>
      {creating && (
        <HomeworkFormDialog
          open
          onOpenChange={setCreating}
          defaultDate={shiftDayKey(todayKey(timeZone), DEFAULT_DUE_DAYS)}
          timeZone={timeZone}
        />
      )}
    </div>
  );
}
