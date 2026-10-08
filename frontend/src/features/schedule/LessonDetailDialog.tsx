import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";

import { errorMessage } from "@/api/errors";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field, Input } from "@/components/ui/input";
import { formatDayLabel, formatTimeRange, minutesBetween, toLocalParts } from "@/lib/datetime";
import { texts } from "@/lib/texts";
import { useSubjectName } from "@/features/reference/api";
import { externalLinkProps } from "@/lib/externalLink";

import { useCancelLesson, useCompleteLesson, useRescheduleLesson } from "./api";
import type { Attendance, Lesson } from "./api";
import { rescheduleFormSchema, toReschedulePayload } from "./forms";
import type { RescheduleFormValues } from "./forms";
import { dialogScroll } from "./LessonFormDialog";

const t = texts.admin.schedule;
const d = t.detail;

type View = "details" | "complete" | "reschedule" | "cancel";

type LessonDetailDialogProps = {
  lesson: Lesson | null;
  timeZone: string;
  onClose: () => void;
};

function statusKey(lesson: Lesson): "lesson.scheduled" | "lesson.completed" | "lesson.cancelled" {
  return `lesson.${lesson.status}`;
}

function ErrorLine({ error }: { error: unknown }) {
  return (
    <p role="alert" className="text-sm text-destructive font-body">
      {errorMessage(error)}
    </p>
  );
}

function Details({
  lesson,
  timeZone,
  onView,
}: {
  lesson: Lesson;
  timeZone: string;
  onView: (view: View) => void;
}) {
  const subjectLabel = useSubjectName();
  const link = (url: string | null) =>
    url === null ? (
      d.none
    ) : (
      <a {...externalLinkProps(url)} className="break-all text-primary underline">
        {url}
      </a>
    );
  return (
    <div className="flex flex-col gap-3 font-body">
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge status={statusKey(lesson)} />
        {lesson.is_detached && (
          <span className="text-xs font-semibold text-muted-foreground">{d.detached}</span>
        )}
      </div>
      <p className="text-sm">{subjectLabel(lesson.subject_code)}</p>
      {lesson.topic !== null && (
        <p className="text-sm">
          <span className="text-muted-foreground">{d.topic}: </span>
          {lesson.topic}
        </p>
      )}
      <div>
        <p className="text-sm font-medium">{d.participants}</p>
        <ul className="mt-1 flex flex-col gap-1">
          {lesson.participants.map((participant) => (
            <li key={participant.student_id} className="flex items-center justify-between gap-2">
              <span>{participant.display_name}</span>
              <StatusBadge status={`attendance.${participant.attendance}`} />
            </li>
          ))}
        </ul>
      </div>
      <div className="text-sm">
        <p>
          <span className="text-muted-foreground">{d.video}: </span>
          {link(lesson.video_url_override)}
        </p>
        <p>
          <span className="text-muted-foreground">{d.board}: </span>
          {link(lesson.board_url_override)}
        </p>
      </div>
      {lesson.teacher_note !== null && (
        <p className="text-sm">
          <span className="text-muted-foreground">{d.note}: </span>
          {lesson.teacher_note}
        </p>
      )}
      {lesson.cancel_reason !== null && (
        <p className="text-sm">
          <span className="text-muted-foreground">{d.cancelReason}: </span>
          {lesson.cancel_reason}
        </p>
      )}
      <span className="sr-only">{timeZone}</span>
      {lesson.status === "scheduled" && (
        <div className="flex flex-col gap-2 pt-2">
          <Button
            variant="primary"
            onClick={() => {
              onView("complete");
            }}
          >
            {d.actions.complete}
          </Button>
          <div className="flex gap-2">
            <Button
              variant="outline"
              className="flex-1"
              onClick={() => {
                onView("reschedule");
              }}
            >
              {d.actions.reschedule}
            </Button>
            <Button
              variant="outline"
              className="flex-1"
              onClick={() => {
                onView("cancel");
              }}
            >
              {d.actions.cancel}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

type Mark = { attendance: Exclude<Attendance, "pending">; billable: boolean };

function CompleteView({
  lesson,
  onDone,
  onBack,
}: {
  lesson: Lesson;
  onDone: () => void;
  onBack: () => void;
}) {
  const complete = useCompleteLesson(lesson.id);
  const [marks, setMarks] = useState<Record<number, Mark>>(() =>
    Object.fromEntries(
      lesson.participants.map((p) => [p.student_id, { attendance: "attended", billable: true }]),
    ),
  );
  const update = (studentId: number, patch: Partial<Mark>) => {
    setMarks((current) => {
      const previous = current[studentId] ?? { attendance: "attended", billable: true };
      return { ...current, [studentId]: { ...previous, ...patch } };
    });
  };
  const options: { value: Mark["attendance"]; label: string }[] = [
    { value: "attended", label: t.complete.attended },
    { value: "no_show", label: t.complete.noShow },
    { value: "cancelled", label: t.complete.cancelled },
  ];
  return (
    <div className="flex flex-col gap-4 font-body">
      {lesson.participants.map((participant) => {
        const mark = marks[participant.student_id] ?? { attendance: "attended", billable: true };
        return (
          <fieldset key={participant.student_id} className="flex flex-col gap-2">
            <legend className="text-sm font-semibold">{participant.display_name}</legend>
            <div className="flex flex-wrap gap-3">
              {options.map((option) => (
                <label key={option.value} className="flex min-h-11 items-center gap-2">
                  <input
                    type="radio"
                    name={`attendance-${String(participant.student_id)}`}
                    className="size-5 accent-primary"
                    checked={mark.attendance === option.value}
                    onChange={() => {
                      update(participant.student_id, {
                        attendance: option.value,
                        billable: option.value === "attended",
                      });
                    }}
                  />
                  {option.label}
                </label>
              ))}
            </div>
            <label className="flex min-h-11 items-center gap-2">
              <input
                type="checkbox"
                className="size-5 accent-primary"
                checked={mark.billable}
                aria-label={`${t.complete.billable}: ${participant.display_name}`}
                onChange={(event) => {
                  update(participant.student_id, { billable: event.target.checked });
                }}
              />
              {t.complete.billable}
            </label>
          </fieldset>
        );
      })}
      {complete.isError && <ErrorLine error={complete.error} />}
      <Button
        variant="primary"
        loading={complete.isPending}
        onClick={() => {
          complete.mutate(
            {
              marks: lesson.participants.map((participant) => {
                const mark = marks[participant.student_id] ?? {
                  attendance: "attended" as const,
                  billable: true,
                };
                return {
                  student_id: participant.student_id,
                  attendance: mark.attendance,
                  is_billable: mark.billable,
                };
              }),
            },
            {
              onSuccess: () => {
                toast.success(t.complete.done);
                onDone();
              },
            },
          );
        }}
      >
        {t.complete.submit}
      </Button>
      <Button variant="ghost" onClick={onBack}>
        {d.back}
      </Button>
    </div>
  );
}

function RescheduleView({
  lesson,
  timeZone,
  onDone,
  onBack,
}: {
  lesson: Lesson;
  timeZone: string;
  onDone: () => void;
  onBack: () => void;
}) {
  const reschedule = useRescheduleLesson(lesson.id);
  const parts = toLocalParts(lesson.start_at, timeZone);
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<RescheduleFormValues>({
    resolver: zodResolver(rescheduleFormSchema),
    defaultValues: {
      date: parts.date,
      time: parts.time,
      duration: String(minutesBetween(lesson.start_at, lesson.end_at)),
    },
  });
  return (
    <form
      noValidate
      className="flex flex-col gap-4"
      onSubmit={(event) => {
        void handleSubmit((values) => {
          reschedule.mutate(toReschedulePayload(values, timeZone), {
            onSuccess: () => {
              toast.success(t.reschedule.done);
              onDone();
            },
          });
        })(event);
      }}
    >
      <Field label={t.form.date} error={errors.date?.message}>
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
      <Field label={t.form.time} hint={t.form.timezoneHint(timeZone)} error={errors.time?.message}>
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
      <Field label={t.form.duration} error={errors.duration?.message}>
        {({ id, invalid, describedBy }) => (
          <Input
            id={id}
            inputMode="numeric"
            invalid={invalid}
            aria-describedby={describedBy}
            {...register("duration")}
          />
        )}
      </Field>
      {reschedule.isError && <ErrorLine error={reschedule.error} />}
      <Button type="submit" variant="primary" loading={reschedule.isPending}>
        {t.reschedule.submit}
      </Button>
      <Button type="button" variant="ghost" onClick={onBack}>
        {d.back}
      </Button>
    </form>
  );
}

function CancelView({
  lesson,
  when,
  onDone,
  onBack,
}: {
  lesson: Lesson;
  when: string;
  onDone: () => void;
  onBack: () => void;
}) {
  const cancel = useCancelLesson(lesson.id);
  const [reason, setReason] = useState("");
  const [billable, setBillable] = useState<number[]>([]);
  return (
    <div className="flex flex-col gap-4 font-body">
      <p className="text-lg font-bold font-heading">{t.cancel.title(when)}</p>
      <p className="text-sm text-muted-foreground">{t.cancel.text}</p>
      <Field label={t.cancel.reason}>
        {({ id }) => (
          <Input
            id={id}
            value={reason}
            maxLength={255}
            onChange={(event) => {
              setReason(event.target.value);
            }}
          />
        )}
      </Field>
      <div className="flex flex-col">
        {lesson.participants.map((participant) => (
          <label key={participant.student_id} className="flex min-h-11 items-center gap-2">
            <input
              type="checkbox"
              className="size-5 accent-primary"
              checked={billable.includes(participant.student_id)}
              aria-label={`${t.cancel.billable}: ${participant.display_name}`}
              onChange={(event) => {
                setBillable((current) =>
                  event.target.checked
                    ? [...current, participant.student_id]
                    : current.filter((id) => id !== participant.student_id),
                );
              }}
            />
            {t.cancel.billable}: {participant.display_name}
          </label>
        ))}
      </div>
      {cancel.isError && <ErrorLine error={cancel.error} />}
      <div className="flex gap-2">
        <Button variant="outline" className="flex-1" onClick={onBack}>
          {texts.common.back}
        </Button>
        <Button
          variant="destructive"
          className="flex-1"
          loading={cancel.isPending}
          onClick={() => {
            cancel.mutate(
              {
                reason: reason.trim() === "" ? null : reason.trim(),
                billable_student_ids: billable,
              },
              {
                onSuccess: () => {
                  toast.success(t.cancel.done);
                  onDone();
                },
              },
            );
          }}
        >
          {t.cancel.submit}
        </Button>
      </div>
    </div>
  );
}

/** Карточка урока и действия над ним: отметка проведения, перенос, отмена (docs/07 §9.2.7). */
export function LessonDetailDialog({ lesson, timeZone, onClose }: LessonDetailDialogProps) {
  const [view, setView] = useState<View>("details");
  const open = lesson !== null;
  const close = () => {
    setView("details");
    onClose();
  };
  const when =
    lesson === null
      ? ""
      : `${formatDayLabel(lesson.start_at, timeZone)}, ${formatTimeRange(lesson.start_at, lesson.end_at, timeZone)}`;
  const back = () => {
    setView("details");
  };
  const titles: Record<View, string> = {
    details: when,
    complete: t.complete.title,
    reschedule: t.reschedule.title,
    cancel: d.actions.cancel,
  };
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) close();
      }}
    >
      <DialogContent className={dialogScroll}>
        {lesson !== null && (
          <>
            <DialogHeader>
              <DialogTitle className="text-lg font-bold font-heading">{titles[view]}</DialogTitle>
              <DialogDescription className="sr-only">{when}</DialogDescription>
            </DialogHeader>
            {view === "details" && <Details lesson={lesson} timeZone={timeZone} onView={setView} />}
            {view === "complete" && <CompleteView lesson={lesson} onDone={close} onBack={back} />}
            {view === "reschedule" && (
              <RescheduleView lesson={lesson} timeZone={timeZone} onDone={close} onBack={back} />
            )}
            {view === "cancel" && (
              <CancelView lesson={lesson} when={when} onDone={close} onBack={back} />
            )}
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
