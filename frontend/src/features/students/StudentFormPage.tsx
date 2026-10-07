import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";

import { errorMessage } from "@/api/errors";
import { ErrorState } from "@/components/common/ErrorState";
import { PageHeader } from "@/components/common/PageHeader";
import { PageSkeleton } from "@/components/common/PageSkeleton";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";
import { useMe } from "@/features/auth/api";
import { useSubjects } from "@/features/reference/api";
import { texts } from "@/lib/texts";
import { cn } from "@/lib/utils";

import { useCreateStudent, useStudent, useUpdateStudent } from "./api";
import type { StudentCard } from "./api";
import {
  EMPTY_STUDENT_FORM,
  TIMEZONES,
  cardToFormValues,
  studentFormSchema,
  toCreatePayload,
  toUpdatePayload,
} from "./studentForm";
import type { StudentFormValues } from "./studentForm";

const t = texts.admin.students;
const f = t.form;

const selectClasses =
  "min-h-12 w-full rounded-md border border-input bg-card px-4 text-base text-foreground font-body focus-visible:border-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

type FormProps = {
  initial: StudentFormValues;
  canEditPrice: boolean;
  submitLabel: string;
  pending: boolean;
  submitError: string | undefined;
  onSubmit: (values: StudentFormValues) => void;
};

/** Форма профиля ученика (docs/07 §9.2.4). Поле цены есть только у владельца. */
export function StudentForm({
  initial,
  canEditPrice,
  submitLabel,
  pending,
  submitError,
  onSubmit,
}: FormProps) {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<StudentFormValues>({
    resolver: zodResolver(studentFormSchema),
    defaultValues: initial,
  });
  const subjects = useSubjects();

  return (
    <form
      noValidate
      className="flex flex-col gap-4"
      onSubmit={(event) => {
        void handleSubmit(onSubmit)(event);
      }}
    >
      <Field label={f.name} error={errors.display_name?.message}>
        {({ id, invalid, describedBy }) => (
          <Input
            id={id}
            invalid={invalid}
            aria-describedby={describedBy}
            autoComplete="off"
            {...register("display_name")}
          />
        )}
      </Field>
      <Field label={f.schoolClass} error={errors.school_class?.message}>
        {({ id, invalid, describedBy }) => (
          <Input
            id={id}
            invalid={invalid}
            aria-describedby={describedBy}
            inputMode="numeric"
            {...register("school_class")}
          />
        )}
      </Field>
      <fieldset className="flex flex-col gap-2">
        <legend className="text-sm font-medium text-foreground font-body">{f.subjects}</legend>
        <div className="flex flex-wrap gap-4">
          {(subjects.data ?? []).map(({ code, name }) => (
            <label key={code} className="flex min-h-11 items-center gap-2 font-body">
              <input
                type="checkbox"
                value={code}
                className="size-5 accent-primary"
                {...register("subject_codes")}
              />
              {name}
            </label>
          ))}
        </div>
      </fieldset>
      <Field label={f.timezone} error={errors.timezone?.message}>
        {({ id, invalid, describedBy }) => (
          <select
            id={id}
            aria-invalid={invalid || undefined}
            aria-describedby={describedBy}
            className={cn(selectClasses)}
            {...register("timezone")}
          >
            {TIMEZONES.map((zone) => (
              <option key={zone} value={zone}>
                {texts.admin.timezones[zone as keyof typeof texts.admin.timezones]}
              </option>
            ))}
          </select>
        )}
      </Field>
      <Field label={f.video} error={errors.video_url?.message}>
        {({ id, invalid, describedBy }) => (
          <Input
            id={id}
            type="url"
            invalid={invalid}
            aria-describedby={describedBy}
            placeholder="https://"
            {...register("video_url")}
          />
        )}
      </Field>
      <Field label={f.board} error={errors.board_url?.message}>
        {({ id, invalid, describedBy }) => (
          <Input
            id={id}
            type="url"
            invalid={invalid}
            aria-describedby={describedBy}
            placeholder="https://"
            {...register("board_url")}
          />
        )}
      </Field>
      {canEditPrice && (
        <Field label={f.price} error={errors.lesson_price?.message}>
          {({ id, invalid, describedBy }) => (
            <Input
              id={id}
              invalid={invalid}
              aria-describedby={describedBy}
              inputMode="numeric"
              {...register("lesson_price")}
            />
          )}
        </Field>
      )}
      <Field label={f.notes} error={errors.teacher_notes?.message}>
        {({ id, invalid, describedBy }) => (
          <textarea
            id={id}
            rows={4}
            aria-invalid={invalid || undefined}
            aria-describedby={describedBy}
            className={cn(selectClasses, "py-3")}
            {...register("teacher_notes")}
          />
        )}
      </Field>
      {submitError !== undefined && (
        <p role="alert" className="text-sm text-destructive font-body">
          {submitError}
        </p>
      )}
      <Button type="submit" variant="primary" loading={pending}>
        {submitLabel}
      </Button>
    </form>
  );
}

function CreateStudent({ canEditPrice }: { canEditPrice: boolean }) {
  const navigate = useNavigate();
  const create = useCreateStudent();
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={f.createTitle} />
      <StudentForm
        initial={EMPTY_STUDENT_FORM}
        canEditPrice={canEditPrice}
        submitLabel={f.submitCreate}
        pending={create.isPending}
        submitError={create.isError ? errorMessage(create.error) : undefined}
        onSubmit={(values) => {
          create.mutate(toCreatePayload(values, canEditPrice), {
            onSuccess: (card) => {
              void navigate(`/admin/students/${String(card.user_id)}`, {
                replace: true,
                state: { invite: true },
              });
            },
          });
        }}
      />
    </div>
  );
}

function EditStudent({ card, canEditPrice }: { card: StudentCard; canEditPrice: boolean }) {
  const navigate = useNavigate();
  const update = useUpdateStudent(card.user_id);
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={f.editTitle} description={card.display_name} />
      <StudentForm
        initial={cardToFormValues(card)}
        canEditPrice={canEditPrice}
        submitLabel={f.submitEdit}
        pending={update.isPending}
        submitError={update.isError ? errorMessage(update.error) : undefined}
        onSubmit={(values) => {
          update.mutate(toUpdatePayload(values, canEditPrice), {
            onSuccess: () => {
              toast.success(texts.messages.saved);
              void navigate(`/admin/students/${String(card.user_id)}`);
            },
          });
        }}
      />
    </div>
  );
}

function EditStudentLoader({ id, canEditPrice }: { id: number; canEditPrice: boolean }) {
  const query = useStudent(id);
  if (query.isPending) return <PageSkeleton />;
  if (query.isError) {
    return (
      <ErrorState
        message={errorMessage(query.error)}
        onRetry={() => {
          void query.refetch();
        }}
      />
    );
  }
  return <EditStudent card={query.data} canEditPrice={canEditPrice} />;
}

/** Маршруты `/admin/students/new` и `/admin/students/:id/edit`. */
export function StudentFormPage() {
  const { id } = useParams();
  const me = useMe();
  const canEditPrice = me.data?.role === "owner";
  if (id === undefined) return <CreateStudent canEditPrice={canEditPrice} />;
  return <EditStudentLoader id={Number(id)} canEditPrice={canEditPrice} />;
}
