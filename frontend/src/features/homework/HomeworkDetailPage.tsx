import { ArrowLeft } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { errorMessage } from "@/api/errors";
import { ErrorState } from "@/components/common/ErrorState";
import { PageHeader } from "@/components/common/PageHeader";
import { PageSkeleton } from "@/components/common/PageSkeleton";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Card } from "@/components/ui/card";
import { useMe } from "@/features/auth/api";
import { formatDate, formatTime } from "@/lib/datetime";
import { texts } from "@/lib/texts";

import { useHomework } from "./api";

const t = texts.admin.homework;

/** Задание и все его выдачи: статусы, сроки, переход к проверке. */
export function HomeworkDetailPage() {
  const params = useParams();
  const { data: me } = useMe();
  const timeZone = me?.timezone ?? "Europe/Moscow";
  const query = useHomework(Number(params["homeworkId"]));

  let content;
  if (query.isPending) {
    content = <PageSkeleton />;
  } else if (query.isError) {
    content = (
      <ErrorState
        message={errorMessage(query.error)}
        onRetry={() => {
          void query.refetch();
        }}
      />
    );
  } else {
    const homework = query.data;
    content = (
      <div className="flex flex-col gap-4">
        {homework.description !== null && (
          <p className="whitespace-pre-wrap text-base font-body">{homework.description}</p>
        )}
        {homework.materials.length > 0 && (
          <p className="text-sm text-muted-foreground font-body">
            {t.detail.materials}: {homework.materials.map((m) => m.original_name).join(", ")}
          </p>
        )}
        <h2 className="text-lg font-bold font-heading">{t.detail.assignments}</h2>
        <ul className="flex flex-col gap-3">
          {homework.assignments.map((row) => (
            <li key={row.id}>
              <Link
                to={`/admin/assignments/${String(row.id)}`}
                className="block rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <Card className="flex flex-col gap-1 p-4">
                  <span className="text-base font-bold font-heading">{row.display_name}</span>
                  <StatusBadge status={`homework.${row.status}`} />
                  <span className="text-sm text-muted-foreground font-body">
                    {t.dueAt(
                      `${formatDate(row.due_at, timeZone)}, ${formatTime(row.due_at, timeZone)}`,
                    )}
                  </span>
                </Card>
              </Link>
            </li>
          ))}
        </ul>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <Link
        to="/admin/homework"
        className="inline-flex min-h-11 items-center gap-1 text-sm font-semibold text-primary font-body"
      >
        <ArrowLeft className="size-4" aria-hidden />
        {t.detail.back}
      </Link>
      <PageHeader title={query.data?.title ?? t.title} />
      {content}
    </div>
  );
}
