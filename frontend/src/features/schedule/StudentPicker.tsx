import { useState } from "react";
import type { UseFormRegisterReturn } from "react-hook-form";

import { errorMessage } from "@/api/errors";
import { ErrorState } from "@/components/common/ErrorState";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useStudents } from "@/features/students/api";
import { texts } from "@/lib/texts";

const t = texts.admin.schedule.form;
const ACTIVE_STUDENTS_LIMIT = 200;

type StudentPickerProps = {
  /** Результат ``register("student_ids")``: чекбоксы с id учеников. */
  field: UseFormRegisterReturn;
  error?: string;
  /** Если задана, показывается кнопка «Выбрать всех»: ей передают id всех активных учеников. */
  onSelectAll?: (ids: string[]) => void;
  /** Подпись группы; по умолчанию — «Участники». */
  legend?: string;
};

/** Мультивыбор участников: список активных учеников с поиском по имени (docs/07 §9.2.6). */
export function StudentPicker({ field, error, onSelectAll, legend }: StudentPickerProps) {
  const [search, setSearch] = useState("");
  const query = useStudents({ status: "active", q: "", limit: ACTIVE_STUDENTS_LIMIT });
  const needle = search.trim().toLowerCase();

  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="text-sm font-medium text-foreground font-body">
        {legend ?? t.participants}
      </legend>
      {query.isPending && <Skeleton className="h-24 w-full" />}
      {query.isError && (
        <ErrorState
          message={errorMessage(query.error)}
          onRetry={() => {
            void query.refetch();
          }}
        />
      )}
      {query.data !== undefined && query.data.items.length === 0 && (
        <p className="text-sm text-muted-foreground font-body">{t.noStudents}</p>
      )}
      {query.data !== undefined && query.data.items.length > 0 && (
        <>
          <Input
            type="search"
            aria-label={t.searchStudents}
            placeholder={t.searchStudents}
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
            }}
          />
          {onSelectAll !== undefined && (
            <Button
              type="button"
              variant="outline"
              size="compact"
              onClick={() => {
                onSelectAll(query.data.items.map((student) => String(student.user_id)));
              }}
            >
              {texts.admin.homework.form.selectAll}
            </Button>
          )}
          <div className="flex max-h-44 flex-col overflow-y-auto rounded-md border border-border">
            {query.data.items.map((student) => (
              <label
                key={student.user_id}
                hidden={needle !== "" && !student.display_name.toLowerCase().includes(needle)}
                className="flex min-h-11 items-center gap-3 px-3 font-body"
              >
                <input
                  type="checkbox"
                  value={String(student.user_id)}
                  className="size-5 accent-primary"
                  {...field}
                />
                {student.display_name}
              </label>
            ))}
          </div>
        </>
      )}
      {error !== undefined && (
        <p role="alert" className="text-sm text-destructive font-body">
          {error}
        </p>
      )}
    </fieldset>
  );
}
