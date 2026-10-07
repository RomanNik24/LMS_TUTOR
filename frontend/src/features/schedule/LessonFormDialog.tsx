import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { toast } from "sonner";

import { errorMessage } from "@/api/errors";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, Input } from "@/components/ui/input";
import { SUBJECT_CODES } from "@/features/students/studentForm";
import { texts } from "@/lib/texts";

import { useCreateLesson } from "./api";
import { DEFAULT_DURATION, lessonFormSchema, toLessonPayload } from "./forms";
import type { LessonFormValues } from "./forms";
import { StudentPicker } from "./StudentPicker";

const t = texts.admin.schedule.form;

export const selectClasses =
  "min-h-12 w-full rounded-md border border-input bg-card px-4 text-base text-foreground font-body focus-visible:border-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";
export const dialogScroll = "max-h-[90dvh] overflow-y-auto";

type LessonFormDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Предзаполненная дата «yyyy-MM-dd» (выбранный день расписания). */
  defaultDate: string;
  timeZone: string;
};

/** Создание урока (docs/07 §9.2.6). Пересечение с другим уроком — «В это время уже есть урок». */
export function LessonFormDialog({
  open,
  onOpenChange,
  defaultDate,
  timeZone,
}: LessonFormDialogProps) {
  const create = useCreateLesson();
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LessonFormValues>({
    resolver: zodResolver(lessonFormSchema),
    defaultValues: {
      subject_code: SUBJECT_CODES[0],
      student_ids: [],
      date: defaultDate,
      time: "17:00",
      duration: DEFAULT_DURATION,
      video_url_override: "",
      board_url_override: "",
      topic: "",
    },
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className={dialogScroll}>
        <DialogHeader>
          <DialogTitle className="text-lg font-bold font-heading">{t.createTitle}</DialogTitle>
        </DialogHeader>
        <form
          noValidate
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            void handleSubmit((values) => {
              create.mutate(toLessonPayload(values, timeZone), {
                onSuccess: () => {
                  toast.success(texts.messages.saved);
                  onOpenChange(false);
                },
              });
            })(event);
          }}
        >
          <Field label={t.subject} error={errors.subject_code?.message}>
            {({ id }) => (
              <select id={id} className={selectClasses} {...register("subject_code")}>
                {SUBJECT_CODES.map((code) => (
                  <option key={code} value={code}>
                    {texts.admin.subjects[code]}
                  </option>
                ))}
              </select>
            )}
          </Field>
          <StudentPicker field={register("student_ids")} error={errors.student_ids?.message} />
          <Field label={t.date} error={errors.date?.message}>
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
          <Field label={t.time} hint={t.timezoneHint(timeZone)} error={errors.time?.message}>
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
          <Field label={t.duration} error={errors.duration?.message}>
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
          <Field label={t.video} error={errors.video_url_override?.message}>
            {({ id, invalid, describedBy }) => (
              <Input
                id={id}
                type="url"
                placeholder="https://"
                invalid={invalid}
                aria-describedby={describedBy}
                {...register("video_url_override")}
              />
            )}
          </Field>
          <Field label={t.board} error={errors.board_url_override?.message}>
            {({ id, invalid, describedBy }) => (
              <Input
                id={id}
                type="url"
                placeholder="https://"
                invalid={invalid}
                aria-describedby={describedBy}
                {...register("board_url_override")}
              />
            )}
          </Field>
          <Field label={t.topic} error={errors.topic?.message}>
            {({ id, invalid, describedBy }) => (
              <Input
                id={id}
                invalid={invalid}
                aria-describedby={describedBy}
                {...register("topic")}
              />
            )}
          </Field>
          {create.isError && (
            <p role="alert" className="text-sm text-destructive font-body">
              {errorMessage(create.error)}
            </p>
          )}
          <Button type="submit" variant="primary" loading={create.isPending}>
            {t.submitCreate}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
