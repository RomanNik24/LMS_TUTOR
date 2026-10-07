import { ArrowLeft, ExternalLink } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";

import { errorMessage } from "@/api/errors";
import { ErrorState } from "@/components/common/ErrorState";
import { PageHeader } from "@/components/common/PageHeader";
import { PageSkeleton } from "@/components/common/PageSkeleton";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useMe } from "@/features/auth/api";
import { formatDate, formatTime } from "@/lib/datetime";
import { texts } from "@/lib/texts";
import { useSubjectName } from "@/features/reference/api";

import { PhotoViewer } from "../PhotoViewer";
import { FileUploader } from "./FileUploader";
import { materialUrl, useSelfReport, useStudentAssignment, useSubmitHomework } from "./studentApi";
import type { StudentAssignmentDetail } from "./studentApi";

const t = texts.student.homework;
const EDITABLE = new Set(["assigned", "needs_revision"]);

function MaterialButton({ id, name }: { id: number; name: string }) {
  const [pending, setPending] = useState(false);
  return (
    <Button
      variant="outline"
      size="compact"
      loading={pending}
      className="justify-start"
      onClick={() => {
        setPending(true);
        materialUrl(id)
          .then((url) => {
            window.open(url, "_blank", "noopener");
          })
          .catch((error: unknown) => {
            toast.error(errorMessage(error));
          })
          .finally(() => {
            setPending(false);
          });
      }}
    >
      <ExternalLink className="size-4" aria-hidden />
      {name}
    </Button>
  );
}

function SolutionBlock({ detail }: { detail: StudentAssignmentDetail }) {
  const [comment, setComment] = useState("");
  const submit = useSubmitHomework(detail.assignment_id);
  const selfReport = useSelfReport(detail.assignment_id);
  const mine = detail.files.filter((file) => file.role === "student_solution");
  const value = comment.trim() === "" ? null : comment.trim();
  const done = () => {
    toast.success(t.submitDone);
  };
  const error = submit.error ?? selfReport.error;

  return (
    <Card className="flex flex-col gap-4 p-4">
      <h2 className="text-lg font-bold font-heading">{t.yourSolution}</h2>
      <FileUploader assignmentId={detail.assignment_id} files={mine} />
      <label className="flex flex-col gap-1.5 text-sm font-medium font-body">
        {t.comment}
        <Input
          value={comment}
          onChange={(event) => {
            setComment(event.target.value);
          }}
        />
      </label>
      {error !== null && (
        <p role="alert" className="text-sm text-destructive font-body">
          {errorMessage(error)}
        </p>
      )}
      <Button
        variant="primary"
        disabled={mine.length === 0}
        loading={submit.isPending}
        onClick={() => {
          submit.mutate(value, { onSuccess: done });
        }}
      >
        {t.submit}
      </Button>
      {mine.length === 0 && (
        <p className="-mt-2 text-sm text-muted-foreground font-body">{t.submitHint}</p>
      )}
      <Button
        variant="outline"
        loading={selfReport.isPending}
        onClick={() => {
          selfReport.mutate(value, { onSuccess: done });
        }}
      >
        {t.selfReport}
      </Button>
      <p className="-mt-2 text-sm text-muted-foreground font-body">{t.selfReportHint}</p>
    </Card>
  );
}

function Body({ detail, timeZone }: { detail: StudentAssignmentDetail; timeZone: string }) {
  const subjectLabel = useSubjectName();
  const status = detail.is_overdue ? "homework.overdue" : (`homework.${detail.status}` as const);
  const mine = detail.files.filter((file) => file.role === "student_solution");
  const reviews = detail.files.filter((file) => file.role === "teacher_review");
  const due = `${formatDate(detail.due_at, timeZone)}, ${formatTime(detail.due_at, timeZone)}`;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-sm bg-muted px-2 text-xs font-semibold leading-6 font-body">
          {subjectLabel(detail.subject_code)}
        </span>
        <StatusBadge status={status} />
        <span className="text-sm text-muted-foreground font-body">{t.dueAt(due)}</span>
      </div>
      {EDITABLE.has(detail.status) && detail.extensions_left > 0 && (
        <p className="text-sm text-muted-foreground font-body">
          {t.extensionsLeft(detail.extensions_left)}
        </p>
      )}
      {detail.description !== null && (
        <p className="whitespace-pre-wrap text-base font-body">{detail.description}</p>
      )}
      {detail.materials.length > 0 && (
        <div className="flex flex-col gap-2">
          <h2 className="text-sm font-semibold font-body">{t.materials}</h2>
          {detail.materials.map((material) => (
            <MaterialButton key={material.id} id={material.id} name={material.original_name} />
          ))}
        </div>
      )}
      {detail.status === "needs_revision" && (
        <div
          role="status"
          className="flex flex-col gap-1 rounded-md bg-warning-bg p-4 text-warning-fg font-body"
        >
          <strong>{t.revision}</strong>
          {detail.teacher_comment !== null && <p>{detail.teacher_comment}</p>}
        </div>
      )}
      {EDITABLE.has(detail.status) && <SolutionBlock detail={detail} />}
      {detail.status === "expired" && (
        <p role="alert" className="rounded-md bg-danger-bg p-4 text-danger-fg font-body">
          {t.expired}
        </p>
      )}
      {detail.status === "submitted" && (
        <Card className="flex flex-col gap-2 p-4">
          <p className="font-semibold font-body">{t.submitted}</p>
          {detail.on_time !== null && (
            <p className="text-sm text-muted-foreground font-body">
              {detail.on_time ? t.submittedOnTime : t.submittedLate}
            </p>
          )}
          <FileUploaderReadOnly detail={detail} />
        </Card>
      )}
      {detail.status === "graded" && detail.score !== null && (
        <Card className="flex flex-col gap-3 p-4">
          <span
            className="self-start rounded-full bg-success-bg px-3 py-1 text-lg font-extrabold text-success-fg font-display"
            aria-label={t.result(detail.score, detail.max_score, detail.score_percent)}
          >
            {t.result(detail.score, detail.max_score, detail.score_percent)}
          </span>
          {detail.teacher_comment !== null && (
            <div className="flex flex-col gap-1">
              <h2 className="text-sm font-semibold font-body">{t.teacherComment}</h2>
              <p className="whitespace-pre-wrap font-body">{detail.teacher_comment}</p>
            </div>
          )}
          {reviews.length > 0 && (
            <div className="flex flex-col gap-2">
              <h2 className="text-sm font-semibold font-body">{t.reviewFiles}</h2>
              <PhotoViewer files={reviews} />
            </div>
          )}
        </Card>
      )}
      {detail.status === "graded" && mine.length > 0 && <FileUploaderReadOnly detail={detail} />}
    </div>
  );
}

function FileUploaderReadOnly({ detail }: { detail: StudentAssignmentDetail }) {
  const mine = detail.files.filter((file) => file.role === "student_solution");
  if (mine.length === 0) return null;
  return <FileUploader assignmentId={detail.assignment_id} files={mine} disabled />;
}

/** Карточка ДЗ и сдача (docs/07 §9.1.5). */
export function StudentHomeworkCardPage() {
  const params = useParams();
  const { data: me } = useMe();
  const timeZone = me?.timezone ?? "Europe/Moscow";
  const query = useStudentAssignment(Number(params["assignmentId"]));

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
    content = <Body detail={query.data} timeZone={timeZone} />;
  }

  return (
    <div className="flex flex-col gap-4">
      <Link
        to="/app/homework"
        className="inline-flex min-h-11 items-center gap-1 text-sm font-semibold text-primary font-body"
      >
        <ArrowLeft className="size-4" aria-hidden />
        {t.back}
      </Link>
      <PageHeader title={query.data?.title ?? t.title} />
      {content}
    </div>
  );
}
