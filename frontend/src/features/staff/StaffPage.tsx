import { zodResolver } from "@hookform/resolvers/zod";
import { UserCog } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { errorMessage } from "@/api/errors";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { PageHeader } from "@/components/common/PageHeader";
import { PageSkeleton } from "@/components/common/PageSkeleton";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, Input } from "@/components/ui/input";
import { InvitationDialog } from "@/features/invitations/InvitationDialog";
import { DEFAULT_TIMEZONE, NAME_MAX_LENGTH, TIMEZONES } from "@/features/students/studentForm";
import { texts } from "@/lib/texts";
import { cn } from "@/lib/utils";

import { useArchiveStaff, useCreateStaff, useStaff, useUpdateStaff } from "./api";
import type { StaffItem } from "./api";

const t = texts.admin.staff;
const f = t.form;

const staffFormSchema = z.object({
  display_name: z.string().trim().min(1, f.nameRequired).max(NAME_MAX_LENGTH, f.nameTooLong),
  role: z.enum(["owner", "manager"]),
  timezone: z.string().min(1),
});
type StaffFormValues = z.infer<typeof staffFormSchema>;

const selectClasses =
  "min-h-12 w-full rounded-md border border-input bg-card px-4 text-base text-foreground font-body focus-visible:border-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

type StaffDialogProps = {
  /** Редактируемый сотрудник; без него — создание. */
  staff: StaffItem | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: (created: StaffItem) => void;
};

function StaffFormDialog({ staff, open, onOpenChange, onCreated }: StaffDialogProps) {
  const create = useCreateStaff();
  const update = useUpdateStaff(staff?.user_id ?? 0);
  const editing = staff !== null;
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<StaffFormValues>({
    resolver: zodResolver(staffFormSchema),
    defaultValues: {
      display_name: staff?.display_name ?? "",
      role: staff?.role === "owner" ? "owner" : "manager",
      timezone: staff?.timezone ?? DEFAULT_TIMEZONE,
    },
  });
  const mutation = editing ? update : create;

  function submit(values: StaffFormValues) {
    if (editing) {
      update.mutate(
        { display_name: values.display_name, role: values.role },
        {
          onSuccess: () => {
            toast.success(texts.messages.saved);
            onOpenChange(false);
          },
        },
      );
    } else {
      create.mutate(values, {
        onSuccess: (created) => {
          onOpenChange(false);
          onCreated(created);
        },
      });
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="text-lg font-bold font-heading">
            {editing ? f.editTitle : f.createTitle}
          </DialogTitle>
        </DialogHeader>
        <form
          noValidate
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            void handleSubmit(submit)(event);
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
          <Field label={f.role}>
            {({ id }) => (
              <select id={id} className={cn(selectClasses)} {...register("role")}>
                <option value="manager">{t.roles.manager}</option>
                <option value="owner">{t.roles.owner}</option>
              </select>
            )}
          </Field>
          {!editing && (
            <Field label={f.timezone}>
              {({ id }) => (
                <select id={id} className={cn(selectClasses)} {...register("timezone")}>
                  {TIMEZONES.map((zone) => (
                    <option key={zone} value={zone}>
                      {texts.admin.timezones[zone as keyof typeof texts.admin.timezones]}
                    </option>
                  ))}
                </select>
              )}
            </Field>
          )}
          {mutation.isError && (
            <p role="alert" className="text-sm text-destructive font-body">
              {errorMessage(mutation.error)}
            </p>
          )}
          <Button type="submit" variant="primary" loading={mutation.isPending}>
            {editing ? f.submitEdit : f.submitCreate}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}

type Action =
  | { type: "create" }
  | { type: "edit"; staff: StaffItem }
  | { type: "invite"; staff: StaffItem }
  | { type: "archive"; staff: StaffItem }
  | null;

/** «Сотрудники» (docs/07 §9.2.13): список, создание с ролью, приглашение, архивация. Только владелец. */
export function StaffPage() {
  const [showArchived, setShowArchived] = useState(false);
  const [action, setAction] = useState<Action>(null);
  const query = useStaff(showArchived);
  const archive = useArchiveStaff();
  const close = () => {
    setAction(null);
  };

  let content;
  if (query.isPending) {
    content = <PageSkeleton />;
  } else if (query.isError) {
    content = (
      <ErrorState
        message={errorMessage(query.error)}
        onRetry={() => {
          void query.refetch();
        }}
      />
    );
  } else if (query.data.items.length === 0) {
    content = <EmptyState icon={UserCog} title={t.empty.title} description={t.empty.text} />;
  } else {
    content = (
      <ul className="flex flex-col gap-3">
        {query.data.items.map((item) => (
          <li key={item.user_id}>
            <Card className="flex flex-col gap-2">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-base font-bold font-heading">{item.display_name}</span>
                <span className="text-sm text-muted-foreground font-body">
                  {t.roles[item.role === "owner" ? "owner" : "manager"]}
                </span>
                {!item.is_active && (
                  <span className="text-xs font-semibold text-muted-foreground font-body">
                    {t.archivedBadge}
                  </span>
                )}
                {item.bot_blocked && <StatusBadge status="bot.blocked" />}
                {item.invite_pending && item.is_active && (
                  <span className="text-xs font-semibold text-warning-fg font-body">
                    {t.invitePending}
                  </span>
                )}
              </div>
              {item.is_active && (
                <div className="flex flex-wrap gap-2">
                  <Button
                    variant="outline"
                    size="compact"
                    onClick={() => {
                      setAction({ type: "edit", staff: item });
                    }}
                  >
                    {t.actions.edit}
                  </Button>
                  <Button
                    variant="outline"
                    size="compact"
                    onClick={() => {
                      setAction({ type: "invite", staff: item });
                    }}
                  >
                    {t.actions.invite}
                  </Button>
                  <Button
                    variant="ghost"
                    size="compact"
                    onClick={() => {
                      setAction({ type: "archive", staff: item });
                    }}
                  >
                    {t.actions.archive}
                  </Button>
                </div>
              )}
            </Card>
          </li>
        ))}
      </ul>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title={texts.nav.admin.staff}
        actions={
          <Button
            variant="primary"
            onClick={() => {
              setAction({ type: "create" });
            }}
          >
            {t.newStaff}
          </Button>
        }
      />
      <label className="flex min-h-11 items-center gap-2 font-body">
        <input
          type="checkbox"
          className="size-5 accent-primary"
          checked={showArchived}
          onChange={(event) => {
            setShowArchived(event.target.checked);
          }}
        />
        {t.showArchived}
      </label>
      {content}
      {(action?.type === "create" || action?.type === "edit") && (
        <StaffFormDialog
          key={action.type === "edit" ? action.staff.user_id : "new"}
          staff={action.type === "edit" ? action.staff : null}
          open
          onOpenChange={(open) => {
            if (!open) close();
          }}
          onCreated={(created) => {
            setAction({ type: "invite", staff: created });
          }}
        />
      )}
      {action?.type === "invite" && (
        <InvitationDialog
          target={{ kind: "staff", id: action.staff.user_id }}
          name={action.staff.display_name}
          open
          onOpenChange={(open) => {
            if (!open) close();
          }}
        />
      )}
      <ConfirmDialog
        open={action?.type === "archive"}
        onOpenChange={(open) => {
          if (!open) close();
        }}
        title={action?.type === "archive" ? t.archiveTitle(action.staff.display_name) : ""}
        description={t.archiveText}
        confirmLabel={t.archiveConfirm}
        loading={archive.isPending}
        onConfirm={() => {
          if (action?.type !== "archive") return;
          archive.mutate(action.staff.user_id, {
            onSuccess: close,
            onError: (error) => {
              toast.error(errorMessage(error));
            },
          });
        }}
      />
    </div>
  );
}
