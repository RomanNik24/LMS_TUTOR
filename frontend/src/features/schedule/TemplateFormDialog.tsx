import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { toast } from "sonner";

import { errorMessage } from "@/api/errors";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, Input } from "@/components/ui/input";
import { SubjectOptions } from "@/features/reference/SubjectOptions";
import { formatDayKey, upcomingWeekdayKeys } from "@/lib/datetime";
import { texts } from "@/lib/texts";

import { useCreateTemplate } from "./api";
import { DEFAULT_DURATION, templateFormSchema, toTemplatePayload } from "./forms";
import type { TemplateFormValues } from "./forms";
import { dialogScroll, selectClasses } from "./LessonFormDialog";
import { StudentPicker } from "./StudentPicker";

const t = texts.admin.schedule.template;
const f = texts.admin.schedule.form;
const PREVIEW_COUNT = 4;

type TemplateFormDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Сегодняшний день пользователя «yyyy-MM-dd»: с него начинается период по умолчанию. */
  todayKey: string;
  timeZone: string;
};

/** Создание шаблона «каждую неделю» с предпросмотром ближайших дат (docs/07 §9.2.6). */
export function TemplateFormDialog({
  open,
  onOpenChange,
  todayKey,
  timeZone,
}: TemplateFormDialogProps) {
  const create = useCreateTemplate();
  const {
    register,
    handleSubmit,
    watch,
    formState: { errors },
  } = useForm<TemplateFormValues>({
    resolver: zodResolver(templateFormSchema),
    defaultValues: {
      subject_code: "",
      student_ids: [],
      weekday: "2",
      time: "17:00",
      duration: DEFAULT_DURATION,
      starts_on: todayKey,
      ends_on: "",
    },
  });
  const weekday = Number(watch("weekday"));
  const startsOn = watch("starts_on");
  const endsOn = watch("ends_on");
  const from = startsOn >= todayKey ? startsOn : todayKey;
  const preview =
    /^\d{4}-\d{2}-\d{2}$/.test(from) && weekday >= 1 && weekday <= 7
      ? upcomingWeekdayKeys(from, weekday, PREVIEW_COUNT, endsOn === "" ? undefined : endsOn)
      : [];
  const periodInvalid = endsOn !== "" && endsOn < startsOn;

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
              if (values.ends_on !== "" && values.ends_on < values.starts_on) return;
              create.mutate(toTemplatePayload(values, timeZone), {
                onSuccess: () => {
                  toast.success(t.created);
                  onOpenChange(false);
                },
              });
            })(event);
          }}
        >
          <Field label={f.subject} error={errors.subject_code?.message}>
            {({ id }) => (
              <select id={id} className={selectClasses} {...register("subject_code")}>
                <SubjectOptions />
              </select>
            )}
          </Field>
          <StudentPicker field={register("student_ids")} error={errors.student_ids?.message} />
          <Field label={t.weekday}>
            {({ id }) => (
              <select id={id} className={selectClasses} {...register("weekday")}>
                {t.weekdays.map((name, index) => (
                  <option key={name} value={String(index + 1)}>
                    {name}
                  </option>
                ))}
              </select>
            )}
          </Field>
          <Field label={f.time} hint={f.timezoneHint(timeZone)} error={errors.time?.message}>
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
          <Field label={f.duration} error={errors.duration?.message}>
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
          <Field label={t.startsOn} error={errors.starts_on?.message}>
            {({ id, invalid, describedBy }) => (
              <Input
                id={id}
                type="date"
                invalid={invalid}
                aria-describedby={describedBy}
                {...register("starts_on")}
              />
            )}
          </Field>
          <Field label={t.endsOn} error={periodInvalid ? t.periodError : undefined}>
            {({ id, invalid, describedBy }) => (
              <Input
                id={id}
                type="date"
                invalid={invalid}
                aria-describedby={describedBy}
                {...register("ends_on")}
              />
            )}
          </Field>
          <div className="rounded-md bg-muted p-3 font-body">
            <p className="text-sm font-medium">{t.preview}</p>
            {preview.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t.previewEmpty}</p>
            ) : (
              <ul className="mt-1 flex flex-wrap gap-2 text-sm" aria-label={t.preview}>
                {preview.map((key) => (
                  <li key={key} className="rounded-sm bg-card px-2 py-1">
                    {formatDayKey(key)}
                  </li>
                ))}
              </ul>
            )}
          </div>
          {create.isError && (
            <p role="alert" className="text-sm text-destructive font-body">
              {errorMessage(create.error)}
            </p>
          )}
          <Button type="submit" variant="primary" loading={create.isPending}>
            {t.submit}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
