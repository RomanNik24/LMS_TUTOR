import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";

import { ApiError, errorMessage } from "@/api/errors";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, Input } from "@/components/ui/input";
import { dialogScroll } from "@/features/schedule/LessonFormDialog";
import { localToUtcIso } from "@/lib/datetime";
import { texts } from "@/lib/texts";

import { MAX_EXTENSIONS, useExtend, useGrade, useReturn, useUploadReviewFile } from "./api";
import type { AssignmentDetail } from "./api";
import { gradeFormSchema, manualDueSchema, returnFormSchema, toReturnPayload } from "./forms";
import type { GradeFormValues, ManualDueValues, ReturnFormValues } from "./forms";

const t = texts.admin.homework.review;

function ErrorLine({ error }: { error: unknown }) {
  return (
    <p role="alert" className="text-sm text-destructive font-body">
      {errorMessage(error)}
    </p>
  );
}

/** Оценка: балл (0..максимум) и комментарий. */
export function GradeForm({ assignment }: { assignment: AssignmentDetail }) {
  const grade = useGrade(assignment.assignment_id);
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<GradeFormValues>({
    resolver: zodResolver(gradeFormSchema(assignment.max_score)),
    defaultValues: {
      score: assignment.score === null ? "" : String(assignment.score),
      comment: assignment.teacher_comment ?? "",
    },
  });
  return (
    <form
      noValidate
      className="flex flex-col gap-3"
      onSubmit={(event) => {
        void handleSubmit((values) => {
          const comment = values.comment.trim();
          grade.mutate(
            { score: Number(values.score), comment: comment === "" ? null : comment },
            {
              onSuccess: () => {
                toast.success(t.saved);
              },
            },
          );
        })(event);
      }}
    >
      <Field
        label={t.score}
        hint={texts.admin.homework.scoreOf(assignment.max_score)}
        error={errors.score?.message}
      >
        {({ id, invalid, describedBy }) => (
          <Input
            id={id}
            inputMode="numeric"
            invalid={invalid}
            aria-describedby={describedBy}
            {...register("score")}
          />
        )}
      </Field>
      <Field label={t.comment} error={errors.comment?.message}>
        {({ id, invalid, describedBy }) => (
          <Input
            id={id}
            invalid={invalid}
            aria-describedby={describedBy}
            {...register("comment")}
          />
        )}
      </Field>
      {grade.isError && <ErrorLine error={grade.error} />}
      <Button type="submit" variant="primary" loading={grade.isPending}>
        {t.save}
      </Button>
    </form>
  );
}

type ReturnDialogProps = {
  assignmentId: number;
  timeZone: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

/** Возврат на доработку: что исправить и (необязательно) новый срок. */
export function ReturnDialog({ assignmentId, timeZone, open, onOpenChange }: ReturnDialogProps) {
  const send = useReturn(assignmentId);
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<ReturnFormValues>({
    resolver: zodResolver(returnFormSchema),
    defaultValues: { comment: "", date: "", time: "" },
  });
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className={dialogScroll}>
        <DialogHeader>
          <DialogTitle className="text-lg font-bold font-heading">{t.returnTitle}</DialogTitle>
        </DialogHeader>
        <form
          noValidate
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            void handleSubmit((values) => {
              send.mutate(toReturnPayload(values, timeZone), {
                onSuccess: () => {
                  toast.success(t.returned);
                  onOpenChange(false);
                },
              });
            })(event);
          }}
        >
          <Field label={t.returnComment} error={errors.comment?.message}>
            {({ id, invalid, describedBy }) => (
              <Input
                id={id}
                invalid={invalid}
                aria-describedby={describedBy}
                {...register("comment")}
              />
            )}
          </Field>
          <Field label={t.returnDue} hint={t.returnDueHint} error={errors.date?.message}>
            {({ id, invalid, describedBy }) => (
              <Input
                id={id}
                type="date"
                invalid={invalid}
                aria-describedby={describedBy}
                {...register("date")}
              />
            )}
          </Field>
          <Field label={texts.admin.homework.form.time} error={errors.time?.message}>
            {({ id, invalid, describedBy }) => (
              <Input
                id={id}
                type="time"
                invalid={invalid}
                aria-describedby={describedBy}
                {...register("time")}
              />
            )}
          </Field>
          {send.isError && <ErrorLine error={send.error} />}
          <Button type="submit" variant="primary" loading={send.isPending}>
            {t.returnSubmit}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** Перенос срока на следующее занятие; если занятия нет — на дату вручную. «Осталось N из 2». */
export function ExtendControl({
  assignment,
  timeZone,
}: {
  assignment: AssignmentDetail;
  timeZone: string;
}) {
  const extend = useExtend(assignment.assignment_id);
  const [manual, setManual] = useState(false);
  const left = MAX_EXTENSIONS - assignment.extensions_count;
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<ManualDueValues>({
    resolver: zodResolver(manualDueSchema),
    defaultValues: { date: "", time: "20:00" },
  });
  const done = () => {
    toast.success(t.extended);
    setManual(false);
  };
  return (
    <div className="flex flex-col gap-2">
      <Button
        variant="outline"
        disabled={left <= 0}
        loading={extend.isPending && !manual}
        onClick={() => {
          extend.mutate(
            {},
            {
              onSuccess: done,
              onError: (error) => {
                if (error instanceof ApiError && error.code === "no_next_lesson") setManual(true);
              },
            },
          );
        }}
      >
        {t.extend}
      </Button>
      <p className="text-sm text-muted-foreground font-body">
        {left > 0 ? t.extendLeft(left, MAX_EXTENSIONS) : t.extendNone}
      </p>
      {manual && left > 0 && (
        <form
          noValidate
          className="flex flex-col gap-3"
          onSubmit={(event) => {
            void handleSubmit((values) => {
              extend.mutate(
                { due_at: localToUtcIso(values.date, values.time, timeZone) },
                { onSuccess: done },
              );
            })(event);
          }}
        >
          <p className="text-sm font-body">{t.extendManual}</p>
          <Field label={texts.admin.homework.form.date} error={errors.date?.message}>
            {({ id, invalid, describedBy }) => (
              <Input
                id={id}
                type="date"
                invalid={invalid}
                aria-describedby={describedBy}
                {...register("date")}
              />
            )}
          </Field>
          <Field label={texts.admin.homework.form.time} error={errors.time?.message}>
            {({ id, invalid, describedBy }) => (
              <Input
                id={id}
                type="time"
                invalid={invalid}
                aria-describedby={describedBy}
                {...register("time")}
              />
            )}
          </Field>
          <Button type="submit" variant="primary" loading={extend.isPending}>
            {t.extendManualSubmit}
          </Button>
        </form>
      )}
      {extend.isError && !manual && <ErrorLine error={extend.error} />}
    </div>
  );
}

/** Добавление файла проверки (фото или pdf с пометками преподавателя). */
export function ReviewFileUpload({ assignmentId }: { assignmentId: number }) {
  const upload = useUploadReviewFile(assignmentId);
  return (
    <div className="flex flex-col gap-2">
      <Field label={t.addReviewFile} hint={texts.admin.homework.form.materialHint}>
        {({ id, describedBy }) => (
          <Input
            id={id}
            type="file"
            accept="image/jpeg,image/png,image/heic,application/pdf"
            aria-describedby={describedBy}
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file === undefined) return;
              upload.mutate(file, {
                onSuccess: () => {
                  toast.success(t.uploaded);
                },
              });
              event.target.value = "";
            }}
          />
        )}
      </Field>
      {upload.isError && <ErrorLine error={upload.error} />}
    </div>
  );
}
