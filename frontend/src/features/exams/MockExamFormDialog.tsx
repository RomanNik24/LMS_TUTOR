import { zodResolver } from "@hookform/resolvers/zod";
import { useForm, useWatch } from "react-hook-form";
import { toast } from "sonner";

import { errorMessage } from "@/api/errors";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, Input } from "@/components/ui/input";
import { useExamTypes } from "@/features/reference/api";
import { dialogScroll, selectClasses } from "@/features/schedule/LessonFormDialog";
import { useStudents } from "@/features/students/api";
import { texts } from "@/lib/texts";

import { useConversionPreview, useCreateMockExam } from "./api";
import { ConversionLine } from "./ConversionLine";
import {
  EMPTY_MOCK_EXAM_FORM,
  mockExamFormSchema,
  toConvertRequest,
  toCreatePayload,
} from "./forms";
import type { MockExamFormValues } from "./forms";

const t = texts.admin.exams.form;
const ACTIVE_STUDENTS_LIMIT = 200;

type MockExamFormDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Предзаполненная дата «yyyy-MM-dd» (сегодня в поясе пользователя). */
  defaultDate: string;
  /** Ученик, выбранный заранее (например, на вкладке карточки ученика). */
  studentId?: number;
};

/** Ввод результата пробника без ДЗ: результат конвертации виден сразу (docs/07 §9.2.10). */
export function MockExamFormDialog({
  open,
  onOpenChange,
  defaultDate,
  studentId,
}: MockExamFormDialogProps) {
  const create = useCreateMockExam();
  const examTypes = useExamTypes();
  const students = useStudents({ status: "active", q: "", limit: ACTIVE_STUDENTS_LIMIT });
  const {
    register,
    handleSubmit,
    setValue,
    control,
    formState: { errors },
  } = useForm<MockExamFormValues>({
    resolver: zodResolver(mockExamFormSchema),
    defaultValues: {
      ...EMPTY_MOCK_EXAM_FORM,
      exam_date: defaultDate,
      student_id: studentId === undefined ? "" : String(studentId),
    },
  });
  const values = useWatch({ control });
  const types = examTypes.data ?? [];
  const exam = types.find((item) => String(item.id) === values.exam_type_id);
  const request = toConvertRequest(
    {
      exam_type_id: values.exam_type_id ?? "",
      exam_date: values.exam_date ?? "",
      primary_score: values.primary_score ?? "",
      max_primary: values.max_primary ?? "",
      geometry_score: values.geometry_score ?? "",
    },
    types,
  );
  const preview = useConversionPreview(request);

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
            void handleSubmit((submitted) => {
              const body = toConvertRequest(submitted, types);
              if (body === null) return;
              create.mutate(toCreatePayload(submitted, body), {
                onSuccess: () => {
                  toast.success(texts.admin.exams.saved);
                  onOpenChange(false);
                },
              });
            })(event);
          }}
        >
          <Field label={t.student} error={errors.student_id?.message}>
            {({ id }) => (
              <select
                id={id}
                className={selectClasses}
                disabled={studentId !== undefined}
                {...register("student_id")}
              >
                <option value="">{t.studentPlaceholder}</option>
                {(students.data?.items ?? []).map((student) => (
                  <option key={student.user_id} value={String(student.user_id)}>
                    {student.display_name}
                  </option>
                ))}
              </select>
            )}
          </Field>
          <Field label={t.exam} error={errors.exam_type_id?.message}>
            {({ id }) => (
              <select
                id={id}
                className={selectClasses}
                {...register("exam_type_id", {
                  // Максимум варианта подставляется официальный: другой отключает шкалу.
                  onChange: (event: { target: { value: string } }) => {
                    const chosen = types.find((item) => String(item.id) === event.target.value);
                    setValue("max_primary", chosen === undefined ? "" : String(chosen.max_primary));
                    setValue("geometry_score", "");
                  },
                })}
              >
                <option value="">{t.examPlaceholder}</option>
                {types.map((item) => (
                  <option key={item.id} value={String(item.id)}>
                    {item.name}
                  </option>
                ))}
              </select>
            )}
          </Field>
          <Field label={t.date} error={errors.exam_date?.message}>
            {({ id, invalid, describedBy }) => (
              <Input
                id={id}
                type="date"
                invalid={invalid}
                aria-describedby={describedBy}
                {...register("exam_date")}
              />
            )}
          </Field>
          <Field label={t.primary} error={errors.primary_score?.message}>
            {({ id, invalid, describedBy }) => (
              <Input
                id={id}
                inputMode="numeric"
                invalid={invalid}
                aria-describedby={describedBy}
                {...register("primary_score")}
              />
            )}
          </Field>
          <Field label={t.max} hint={t.maxHint} error={errors.max_primary?.message}>
            {({ id, invalid, describedBy }) => (
              <Input
                id={id}
                inputMode="numeric"
                invalid={invalid}
                aria-describedby={describedBy}
                {...register("max_primary")}
              />
            )}
          </Field>
          {exam?.uses_geometry === true && (
            <Field label={t.geometry} hint={t.geometryHint} error={errors.geometry_score?.message}>
              {({ id, invalid, describedBy }) => (
                <Input
                  id={id}
                  inputMode="numeric"
                  invalid={invalid}
                  aria-describedby={describedBy}
                  {...register("geometry_score")}
                />
              )}
            </Field>
          )}
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
          {exam !== undefined && request !== null && preview.data !== undefined && (
            <div className="rounded-md bg-muted p-3">
              <p className="text-sm text-muted-foreground font-body">{t.conversion}</p>
              <ConversionLine
                conversion={preview.data}
                examType={exam}
                primaryScore={request.primary_score}
              />
            </div>
          )}
          {preview.isError && (
            <p role="alert" className="text-sm text-destructive font-body">
              {errorMessage(preview.error)}
            </p>
          )}
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
