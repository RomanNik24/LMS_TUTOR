import { ClipboardCheck, Plus } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { errorMessage } from "@/api/errors";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { PageHeader } from "@/components/common/PageHeader";
import { PageSkeleton } from "@/components/common/PageSkeleton";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useMe } from "@/features/auth/api";
import { useExamTypes } from "@/features/reference/api";
import { selectClasses } from "@/features/schedule/LessonFormDialog";
import { useStudents } from "@/features/students/api";
import { DEFAULT_TIMEZONE } from "@/features/students/studentForm";
import { formatDate, todayKey } from "@/lib/datetime";
import { texts } from "@/lib/texts";

import { PAGE_SIZE, useDeleteMockExam, useMockExams } from "./api";
import type { MockExam } from "./api";
import { MockExamFormDialog } from "./MockExamFormDialog";

const t = texts.admin.exams;
const ACTIVE_STUDENTS_LIMIT = 200;

function resultText(item: MockExam, kind: "grade_2_5" | "test_100" | undefined): string {
  if (!item.scale_applicable || item.converted_value === null) return texts.exams.notApplicable;
  return kind === "grade_2_5"
    ? texts.exams.gradeLabel(item.converted_value)
    : texts.exams.testLabel(item.converted_value);
}

/** Раздел «Пробники» админки: список результатов с фильтрами и ввод нового (docs/07 §9.2.10). */
export function AdminExamsPage() {
  const { data: me } = useMe();
  const timeZone = me?.timezone ?? DEFAULT_TIMEZONE;
  const [studentId, setStudentId] = useState<number | null>(null);
  const [examTypeId, setExamTypeId] = useState<number | null>(null);
  const [limit, setLimit] = useState(PAGE_SIZE);
  const [creating, setCreating] = useState(false);
  const [deleting, setDeleting] = useState<MockExam | null>(null);
  const query = useMockExams({ studentId, examTypeId, limit });
  const examTypes = useExamTypes();
  const students = useStudents({ status: "active", q: "", limit: ACTIVE_STUDENTS_LIMIT });
  const remove = useDeleteMockExam();
  const kindOf = (id: number) => examTypes.data?.find((item) => item.id === id)?.result_kind;

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
            {t.newResult}
          </Button>
        }
      />
      <div className="flex flex-col gap-2 sm:flex-row">
        <label className="flex flex-1 flex-col gap-1 text-sm font-medium font-body">
          {t.filterStudent}
          <select
            className={selectClasses}
            value={studentId === null ? "" : String(studentId)}
            onChange={(event) => {
              setStudentId(event.target.value === "" ? null : Number(event.target.value));
              setLimit(PAGE_SIZE);
            }}
          >
            <option value="">{t.all}</option>
            {(students.data?.items ?? []).map((student) => (
              <option key={student.user_id} value={String(student.user_id)}>
                {student.display_name}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-1 flex-col gap-1 text-sm font-medium font-body">
          {t.filterExam}
          <select
            className={selectClasses}
            value={examTypeId === null ? "" : String(examTypeId)}
            onChange={(event) => {
              setExamTypeId(event.target.value === "" ? null : Number(event.target.value));
              setLimit(PAGE_SIZE);
            }}
          >
            <option value="">{t.all}</option>
            {(examTypes.data ?? []).map((item) => (
              <option key={item.id} value={String(item.id)}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
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
      {query.data?.items.length === 0 && (
        <EmptyState icon={ClipboardCheck} title={t.title} description={t.empty} />
      )}
      {query.data !== undefined && query.data.items.length > 0 && (
        <ul className="flex flex-col gap-2">
          {query.data.items.map((item) => (
            <li key={item.id}>
              <Card className="flex flex-col gap-2">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <p className="text-base font-bold font-heading">{item.student_name}</p>
                  <p className="text-sm text-muted-foreground font-body">
                    {formatDate(`${item.exam_date}T12:00:00Z`, "UTC")}
                  </p>
                </div>
                <p className="text-sm font-body">{item.exam_type_name}</p>
                <p className="text-sm font-body">
                  {t.row(item.primary_score, item.max_primary)} ·{" "}
                  <span className="font-bold">{resultText(item, kindOf(item.exam_type_id))}</span>
                </p>
                {item.warning === "geometry_missing" && (
                  <p className="text-sm text-warning-fg font-body">{texts.exams.geometryMissing}</p>
                )}
                {item.assignment_id !== null ? (
                  <p className="text-sm text-muted-foreground font-body">{t.fromHomework}</p>
                ) : (
                  <div>
                    <Button
                      variant="ghost"
                      size="compact"
                      onClick={() => {
                        setDeleting(item);
                      }}
                    >
                      {t.delete}
                    </Button>
                  </div>
                )}
              </Card>
            </li>
          ))}
        </ul>
      )}
      {query.data !== undefined && query.data.total > query.data.items.length && (
        <Button
          variant="outline"
          onClick={() => {
            setLimit((value) => value + PAGE_SIZE);
          }}
        >
          {t.loadMore}
        </Button>
      )}
      {creating && (
        <MockExamFormDialog
          open
          onOpenChange={setCreating}
          defaultDate={todayKey(timeZone)}
          studentId={studentId ?? undefined}
        />
      )}
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => {
          if (!open) setDeleting(null);
        }}
        title={t.deleteTitle}
        confirmLabel={t.deleteConfirm}
        loading={remove.isPending}
        onConfirm={() => {
          if (deleting === null) return;
          remove.mutate(deleting.id, {
            onSuccess: () => {
              toast.success(t.deleted);
              setDeleting(null);
            },
            onError: (error) => {
              toast.error(errorMessage(error));
              setDeleting(null);
            },
          });
        }}
      />
    </div>
  );
}
