import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";

import { errorMessage } from "@/api/errors";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, Input } from "@/components/ui/input";
import { dialogScroll, selectClasses } from "@/features/schedule/LessonFormDialog";
import { StudentPicker } from "@/features/schedule/StudentPicker";
import { SubjectOptions } from "@/features/reference/SubjectOptions";
import { texts } from "@/lib/texts";

import { useCreateHomework, useUploadMaterial } from "./api";
import { DEFAULT_DUE_TIME, homeworkFormSchema, toHomeworkPayload } from "./forms";
import type { HomeworkFormValues } from "./forms";

const t = texts.admin.homework.form;

type HomeworkFormDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Предзаполненная дата срока «yyyy-MM-dd» (сегодня + неделя). */
  defaultDate: string;
  timeZone: string;
};

/** Создание ДЗ и выдача ученикам (docs/07 §9.2.8). Материал — необязательный файл. */
export function HomeworkFormDialog({
  open,
  onOpenChange,
  defaultDate,
  timeZone,
}: HomeworkFormDialogProps) {
  const create = useCreateHomework();
  const uploadMaterial = useUploadMaterial();
  const [file, setFile] = useState<File | null>(null);
  const {
    register,
    handleSubmit,
    setValue,
    formState: { errors },
  } = useForm<HomeworkFormValues>({
    resolver: zodResolver(homeworkFormSchema),
    defaultValues: {
      title: "",
      description: "",
      subject_code: "",
      max_score: "5",
      due_mode: "next_lesson",
      date: defaultDate,
      time: DEFAULT_DUE_TIME,
      student_ids: [],
    },
  });

  const submit = handleSubmit(async (values) => {
    try {
      const homework = await create.mutateAsync(toHomeworkPayload(values, timeZone));
      if (file !== null) {
        try {
          await uploadMaterial.mutateAsync({ homeworkId: homework.id, file });
        } catch {
          toast.error(t.materialFailed);
          onOpenChange(false);
          return;
        }
      }
      toast.success(t.created);
      onOpenChange(false);
    } catch {
      // Ошибка создания показана ниже через create.error
    }
  });

  const pending = create.isPending || uploadMaterial.isPending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className={dialogScroll}>
        <DialogHeader>
          <DialogTitle className="text-lg font-bold font-heading">{t.title}</DialogTitle>
        </DialogHeader>
        <form
          noValidate
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            void submit(event);
          }}
        >
          <Field label={t.kind}>
            {({ id }) => (
              <select id={id} className={selectClasses} disabled defaultValue="regular">
                <option value="regular">{texts.admin.homework.kind.regular}</option>
              </select>
            )}
          </Field>
          <Field label={t.name} error={errors.title?.message}>
            {({ id, invalid, describedBy }) => (
              <Input
                id={id}
                invalid={invalid}
                aria-describedby={describedBy}
                {...register("title")}
              />
            )}
          </Field>
          <Field label={t.description} error={errors.description?.message}>
            {({ id, invalid, describedBy }) => (
              <Input
                id={id}
                invalid={invalid}
                aria-describedby={describedBy}
                {...register("description")}
              />
            )}
          </Field>
          <Field label={t.subject} error={errors.subject_code?.message}>
            {({ id }) => (
              <select id={id} className={selectClasses} {...register("subject_code")}>
                <SubjectOptions />
              </select>
            )}
          </Field>
          <Field label={t.maxScore} hint={t.maxScoreHint} error={errors.max_score?.message}>
            {({ id, invalid, describedBy }) => (
              <Input
                id={id}
                inputMode="numeric"
                invalid={invalid}
                aria-describedby={describedBy}
                {...register("max_score")}
              />
            )}
          </Field>
          <Field label={t.dueMode}>
            {({ id }) => (
              <select id={id} className={selectClasses} {...register("due_mode")}>
                <option value="next_lesson">{t.dueNextLesson}</option>
                <option value="fixed">{t.dueFixed}</option>
              </select>
            )}
          </Field>
          <Field label={t.date} hint={t.fallbackHint} error={errors.date?.message}>
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
          <Field label={t.time} error={errors.time?.message}>
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
          <Field label={t.material} hint={t.materialHint}>
            {({ id, describedBy }) => (
              <Input
                id={id}
                type="file"
                accept="image/jpeg,image/png,image/heic,application/pdf"
                aria-describedby={describedBy}
                onChange={(event) => {
                  setFile(event.target.files?.[0] ?? null);
                }}
              />
            )}
          </Field>
          <StudentPicker
            legend={t.students}
            field={register("student_ids")}
            error={errors.student_ids?.message}
            onSelectAll={(ids) => {
              setValue("student_ids", ids, { shouldValidate: true });
            }}
          />
          {create.isError && (
            <p role="alert" className="text-sm text-destructive font-body">
              {errorMessage(create.error)}
            </p>
          )}
          <Button type="submit" variant="primary" loading={pending}>
            {t.submit}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
