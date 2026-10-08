import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { errorMessage } from "@/api/errors";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, Input } from "@/components/ui/input";
import { dialogScroll } from "@/features/schedule/LessonFormDialog";
import { texts } from "@/lib/texts";
import { cn } from "@/lib/utils";

import { useCreateCatalogItem, useUpdateCatalogItem } from "./api";
import type { CatalogItem } from "./api";

const t = texts.admin.catalog.form;

export const TITLE_MAX = 150;
export const DESCRIPTION_MAX = 5000;
export const PRICE_MAX = 100;

export const catalogFormSchema = z.object({
  title: z.string().trim().min(1, t.titleRequired).max(TITLE_MAX, t.titleTooLong),
  description: z
    .string()
    .trim()
    .min(1, t.descriptionRequired)
    .max(DESCRIPTION_MAX, t.descriptionTooLong),
  price_text: z.string().trim().max(PRICE_MAX, t.priceTooLong),
  is_published: z.boolean(),
});
export type CatalogFormValues = z.infer<typeof catalogFormSchema>;

const textareaClasses =
  "min-h-32 w-full rounded-md border border-input bg-card px-4 py-3 text-base text-foreground font-body focus-visible:border-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

type CatalogFormDialogProps = {
  /** Редактируемая карточка; без неё — создание. */
  item: CatalogItem | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

/** Создание и правка карточки каталога. Пустая стоимость очищается (`null`). */
export function CatalogFormDialog({ item, open, onOpenChange }: CatalogFormDialogProps) {
  const create = useCreateCatalogItem();
  const update = useUpdateCatalogItem();
  const editing = item !== null;
  const mutation = editing ? update : create;
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<CatalogFormValues>({
    resolver: zodResolver(catalogFormSchema),
    defaultValues: {
      title: item?.title ?? "",
      description: item?.description ?? "",
      price_text: item?.price_text ?? "",
      is_published: item?.is_published ?? false,
    },
  });

  function submit(values: CatalogFormValues) {
    const body = { ...values, price_text: values.price_text === "" ? null : values.price_text };
    const options = {
      onSuccess: () => {
        toast.success(texts.admin.catalog.saved);
        onOpenChange(false);
      },
    };
    if (item === null) create.mutate(body, options);
    else update.mutate({ id: item.id, body }, options);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className={dialogScroll}>
        <DialogHeader>
          <DialogTitle className="text-lg font-bold font-heading">
            {editing ? t.editTitle : t.createTitle}
          </DialogTitle>
        </DialogHeader>
        <form
          noValidate
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            void handleSubmit(submit)(event);
          }}
        >
          <Field label={t.title} error={errors.title?.message}>
            {({ id, invalid, describedBy }) => (
              <Input
                id={id}
                invalid={invalid}
                aria-describedby={describedBy}
                autoComplete="off"
                {...register("title")}
              />
            )}
          </Field>
          <Field label={t.description} error={errors.description?.message}>
            {({ id, invalid, describedBy }) => (
              <textarea
                id={id}
                aria-invalid={invalid || undefined}
                aria-describedby={describedBy}
                className={cn(textareaClasses)}
                {...register("description")}
              />
            )}
          </Field>
          <Field label={t.price} error={errors.price_text?.message}>
            {({ id, invalid, describedBy }) => (
              <Input
                id={id}
                invalid={invalid}
                aria-describedby={describedBy}
                autoComplete="off"
                placeholder={t.pricePlaceholder}
                {...register("price_text")}
              />
            )}
          </Field>
          <label className="flex min-h-11 items-center gap-3 text-sm font-medium font-body">
            <input
              type="checkbox"
              className="size-5 accent-primary"
              {...register("is_published")}
            />
            {t.publish}
          </label>
          {mutation.isError && (
            <p role="alert" className="text-sm text-destructive font-body">
              {errorMessage(mutation.error)}
            </p>
          )}
          <Button type="submit" variant="primary" loading={mutation.isPending}>
            {editing ? t.submitEdit : t.submitCreate}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
