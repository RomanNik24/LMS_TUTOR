import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { errorMessage } from "@/api/errors";
import { PageHeader } from "@/components/common/PageHeader";
import { PageSkeleton } from "@/components/common/PageSkeleton";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Field, Input } from "@/components/ui/input";
import { useLogout, useMe } from "@/features/auth/api";
import type { Me } from "@/features/auth/api";
import { TIMEZONES } from "@/features/students/studentForm";
import { texts } from "@/lib/texts";

import { useUpdateMe } from "./api";
import { profileFormSchema } from "./profileForm";
import type { ProfileFormValues } from "./profileForm";

const t = texts.profile;
const BOT_USERNAME = import.meta.env.VITE_BOT_USERNAME;

function zoneLabel(zone: string): string {
  return zone in texts.admin.timezones
    ? texts.admin.timezones[zone as keyof typeof texts.admin.timezones]
    : zone;
}

function ProfileForm({ me }: { me: Me }) {
  const update = useUpdateMe();
  // Текущий пояс пользователя может не входить в список: показываем и его.
  const zones = TIMEZONES.includes(me.timezone) ? TIMEZONES : [me.timezone, ...TIMEZONES];
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<ProfileFormValues>({
    resolver: zodResolver(profileFormSchema),
    defaultValues: { display_name: me.display_name, timezone: me.timezone },
  });

  return (
    <form
      noValidate
      className="flex flex-col gap-4"
      onSubmit={(event) => {
        void handleSubmit((values) => {
          update.mutate(values, {
            onSuccess: () => {
              toast.success(texts.messages.saved);
            },
          });
        })(event);
      }}
    >
      <Field label={t.name} error={errors.display_name?.message}>
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
      <Field label={t.timezone} hint={t.timezoneHint}>
        {({ id, describedBy }) => (
          <select
            id={id}
            aria-describedby={describedBy}
            className="min-h-12 w-full rounded-md border border-input bg-card px-4 text-base text-foreground font-body focus-visible:border-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            {...register("timezone")}
          >
            {zones.map((zone) => (
              <option key={zone} value={zone}>
                {zoneLabel(zone)}
              </option>
            ))}
          </select>
        )}
      </Field>
      {update.isError && (
        <p role="alert" className="text-sm text-destructive font-body">
          {errorMessage(update.error)}
        </p>
      )}
      <Button type="submit" variant="primary" loading={update.isPending}>
        {t.save}
      </Button>
    </form>
  );
}

/** Профиль (docs/07 §9.1.7): имя, часовой пояс, «Войти в браузере», выход. Без финансов. */
export function ProfilePage() {
  const { data: me } = useMe();
  const logout = useLogout();
  const navigate = useNavigate();
  if (me === undefined) return <PageSkeleton cards={1} />;
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t.title} />
      <Card>
        <ProfileForm me={me} />
      </Card>
      <Card className="flex flex-col gap-3">
        <h2 className="text-lg font-bold font-heading">{t.webLogin}</h2>
        <p className="text-sm text-muted-foreground font-body">{t.webLoginHint}</p>
        {BOT_USERNAME !== undefined && BOT_USERNAME !== "" && (
          <Button asChild variant="outline">
            <a href={`https://t.me/${BOT_USERNAME}`} target="_blank" rel="noopener noreferrer">
              {t.openBot}
            </a>
          </Button>
        )}
      </Card>
      <Button
        variant="outline"
        loading={logout.isPending}
        onClick={() => {
          logout.mutate(undefined, {
            onSuccess: () => {
              void navigate("/login", { replace: true });
            },
            onError: () => {
              toast.error(t.logoutFailed);
            },
          });
        }}
      >
        {t.logout}
      </Button>
    </div>
  );
}
