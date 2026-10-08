import { ArrowLeft } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { errorMessage } from "@/api/errors";
import { ErrorState } from "@/components/common/ErrorState";
import { PageHeader } from "@/components/common/PageHeader";
import { PageSkeleton } from "@/components/common/PageSkeleton";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useMe } from "@/features/auth/api";
import { formatDate, formatTime } from "@/lib/datetime";
import { texts } from "@/lib/texts";

import { useAssignment } from "./api";
import type { AssignmentDetail } from "./api";
import { ExtendControl, GradeForm, ReturnDialog, ReviewFileUpload } from "./ReviewActions";
import { PhotoViewer } from "./PhotoViewer";

const t = texts.admin.homework.review;
const GRADEABLE = new Set(["submitted", "graded", "expired"]);
const EXTENDABLE = new Set(["assigned", "needs_revision"]);

function stamp(iso: string, timeZone: string): string {
  return `${formatDate(iso, timeZone)}, ${formatTime(iso, timeZone)}`;
}

function Body({ assignment, timeZone }: { assignment: AssignmentDetail; timeZone: string }) {
  const [returning, setReturning] = useState(false);
  const solution = assignment.files.filter((file) => file.role === "student_solution");
  const reviews = assignment.files.filter((file) => file.role === "teacher_review");
  const status = assignment.is_overdue
    ? "homework.overdue"
    : (`homework.${assignment.status}` as const);

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Card className="flex flex-col gap-3 p-4">
        <h2 className="text-lg font-bold font-heading">{t.studentFiles}</h2>
        {solution.length === 0 ? (
          <p className="text-sm text-muted-foreground font-body">{t.noFiles}</p>
        ) : (
          <PhotoViewer files={solution} />
        )}
        {assignment.student_comment !== null && (
          <div className="flex flex-col gap-1">
            <h3 className="text-sm font-semibold font-body">{t.studentComment}</h3>
            <p className="whitespace-pre-wrap text-base font-body">{assignment.student_comment}</p>
          </div>
        )}
        {assignment.on_time !== null && (
          <p className="text-sm text-muted-foreground font-body">
            {assignment.on_time ? t.onTime : t.late}
          </p>
        )}
      </Card>
      <Card className="flex flex-col gap-4 p-4">
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge status={status} />
          <span className="text-sm text-muted-foreground font-body">
            {texts.admin.homework.dueAt(stamp(assignment.due_at, timeZone))}
          </span>
        </div>
        {assignment.score !== null && (
          <p className="text-base font-semibold font-body">
            {t.graded(assignment.score, assignment.max_score, assignment.score_percent)}
          </p>
        )}
        {GRADEABLE.has(assignment.status) && (
          <>
            <GradeForm
              key={assignment.score ?? "new"}
              assignment={assignment}
              timeZone={timeZone}
            />
            {assignment.status === "submitted" && (
              <Button
                variant="outline"
                onClick={() => {
                  setReturning(true);
                }}
              >
                {t.returnButton}
              </Button>
            )}
          </>
        )}
        {EXTENDABLE.has(assignment.status) && (
          <ExtendControl assignment={assignment} timeZone={timeZone} />
        )}
        {!GRADEABLE.has(assignment.status) && !EXTENDABLE.has(assignment.status) && (
          <p className="text-sm text-muted-foreground font-body">{t.notReviewable}</p>
        )}
        <div className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold font-body">{t.reviewFiles}</h3>
          {reviews.length > 0 && <PhotoViewer files={reviews} />}
          <ReviewFileUpload assignmentId={assignment.assignment_id} />
        </div>
        {assignment.extensions.length > 0 && (
          <div className="flex flex-col gap-1">
            <h3 className="text-sm font-semibold font-body">{t.extensionsLog}</h3>
            <ul className="text-sm text-muted-foreground font-body">
              {assignment.extensions.map((row) => (
                <li key={row.created_at}>
                  {t.extensionRow(stamp(row.old_due_at, timeZone), stamp(row.new_due_at, timeZone))}
                </li>
              ))}
            </ul>
          </div>
        )}
      </Card>
      <ReturnDialog
        assignmentId={assignment.assignment_id}
        timeZone={timeZone}
        open={returning}
        onOpenChange={setReturning}
      />
    </div>
  );
}

/** Экран проверки (docs/07 §9.2.9): файлы ученика, балл, комментарий, возврат, перенос срока. */
export function ReviewPage() {
  const params = useParams();
  const assignmentId = Number(params["assignmentId"]);
  const { data: me } = useMe();
  const query = useAssignment(assignmentId);
  const timeZone = me?.timezone ?? "Europe/Moscow";

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
    content = <Body assignment={query.data} timeZone={timeZone} />;
  }

  return (
    <div className="flex flex-col gap-4">
      <Link
        to="/admin/homework"
        className="inline-flex min-h-11 items-center gap-1 text-sm font-semibold text-primary font-body"
      >
        <ArrowLeft className="size-4" aria-hidden />
        {t.back}
      </Link>
      <PageHeader
        title={t.title}
        description={
          query.data === undefined ? undefined : `${query.data.student_name} · ${query.data.title}`
        }
      />
      {content}
    </div>
  );
}
