import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";

import { errorMessage } from "@/api/errors";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { ErrorState } from "@/components/common/ErrorState";
import { PageHeader } from "@/components/common/PageHeader";
import { PageSkeleton } from "@/components/common/PageSkeleton";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { InvitationDialog } from "@/features/invitations/InvitationDialog";
import { texts } from "@/lib/texts";

import { useArchiveStudent, useRestoreStudent, useStudent, useUnlinkTelegram } from "./api";
import type { StudentCard } from "./api";

const t = texts.admin.students;
const o = t.overview;

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5 sm:flex-row sm:gap-4">
      <dt className="w-48 shrink-0 text-sm text-muted-foreground font-body">{label}</dt>
      <dd className="min-w-0 break-words font-body">{children}</dd>
    </div>
  );
}

function LinkValue({ url }: { url: string | null }) {
  if (url === null) return <>{o.none}</>;
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      className="text-primary underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      {url}
    </a>
  );
}

function subjectLabel(code: string): string {
  return code in texts.admin.subjects
    ? texts.admin.subjects[code as keyof typeof texts.admin.subjects]
    : code;
}

function zoneLabel(zone: string): string {
  return zone in texts.admin.timezones
    ? texts.admin.timezones[zone as keyof typeof texts.admin.timezones]
    : zone;
}

function Overview({ card }: { card: StudentCard }) {
  return (
    <Card>
      <h2 className="mb-3 text-lg font-bold font-heading">{o.profile}</h2>
      <dl className="flex flex-col gap-3">
        <Row label={o.subjects}>
          {card.subjects.length === 0 ? o.none : card.subjects.map(subjectLabel).join(", ")}
        </Row>
        <Row label={o.timezone}>{zoneLabel(card.timezone)}</Row>
        <Row label={o.video}>
          <LinkValue url={card.video_url} />
        </Row>
        <Row label={o.board}>
          <LinkValue url={card.board_url} />
        </Row>
        <Row label={o.telegram}>
          {card.telegram_linked ? o.telegramLinked : o.telegramNotLinked}
        </Row>
        <Row label={o.notes}>
          <span className="whitespace-pre-wrap">{card.teacher_notes ?? o.none}</span>
          <span className="block text-xs text-muted-foreground">{o.notesPrivate}</span>
        </Row>
      </dl>
    </Card>
  );
}

function Finance({ card }: { card: Extract<StudentCard, { lesson_price: number }> }) {
  return (
    <Card>
      <dl>
        <Row label={t.finance.lessonPrice}>
          {t.finance.perLesson(card.lesson_price.toLocaleString("ru-RU"))}
        </Row>
      </dl>
    </Card>
  );
}

function isInviteState(state: unknown): boolean {
  if (typeof state !== "object" || state === null) return false;
  return (state as Partial<Record<string, unknown>>)["invite"] === true;
}

type Dialogs = "archive" | "unlink" | "invite" | null;

function CardView({ card }: { card: StudentCard }) {
  const navigate = useNavigate();
  const location = useLocation();
  const [dialog, setDialog] = useState<Dialogs>(null);
  const archive = useArchiveStudent(card.user_id);
  const restore = useRestoreStudent(card.user_id);
  const unlink = useUnlinkTelegram(card.user_id);

  // После создания ученика открываем приглашение (state передаёт форма).
  const inviteRequested = isInviteState(location.state);
  useEffect(() => {
    if (inviteRequested) {
      setDialog("invite");
      void navigate(location.pathname, { replace: true, state: null });
    }
  }, [inviteRequested, location.pathname, navigate]);

  const fail = (error: unknown) => {
    toast.error(errorMessage(error));
  };

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title={card.display_name}
        description={card.school_class === null ? undefined : t.classLabel(card.school_class)}
        actions={
          <Button asChild variant="outline" size="compact">
            <Link to="/admin/students">{t.actions.back}</Link>
          </Button>
        }
      />
      <div className="flex flex-wrap items-center gap-2">
        {!card.is_active && (
          <span className="text-sm font-semibold text-muted-foreground font-body">
            {t.archivedBadge}
          </span>
        )}
        {card.bot_blocked && <StatusBadge status="bot.blocked" />}
      </div>
      <div className="flex flex-wrap gap-2">
        <Button asChild variant="primary" size="compact">
          <Link to={`/admin/students/${String(card.user_id)}/edit`}>{t.actions.edit}</Link>
        </Button>
        {card.is_active && (
          <Button
            variant="outline"
            size="compact"
            onClick={() => {
              setDialog("invite");
            }}
          >
            {t.actions.invite}
          </Button>
        )}
        {card.telegram_linked && (
          <Button
            variant="outline"
            size="compact"
            onClick={() => {
              setDialog("unlink");
            }}
          >
            {t.actions.unlink}
          </Button>
        )}
        {card.is_active ? (
          <Button
            variant="ghost"
            size="compact"
            onClick={() => {
              setDialog("archive");
            }}
          >
            {t.actions.archive}
          </Button>
        ) : (
          <Button
            variant="outline"
            size="compact"
            loading={restore.isPending}
            onClick={() => {
              restore.mutate(undefined, { onError: fail });
            }}
          >
            {t.actions.restore}
          </Button>
        )}
      </div>
      <Tabs defaultValue="overview">
        <TabsList>
          <TabsTrigger value="overview">{t.tabs.overview}</TabsTrigger>
          {"lesson_price" in card && <TabsTrigger value="finance">{t.tabs.finance}</TabsTrigger>}
        </TabsList>
        <TabsContent value="overview">
          <Overview card={card} />
        </TabsContent>
        {"lesson_price" in card && (
          <TabsContent value="finance">
            <Finance card={card} />
          </TabsContent>
        )}
      </Tabs>
      <ConfirmDialog
        open={dialog === "archive"}
        onOpenChange={(open) => {
          setDialog(open ? "archive" : null);
        }}
        title={t.archiveTitle(card.display_name)}
        description={t.archiveText}
        confirmLabel={t.archiveConfirm}
        loading={archive.isPending}
        onConfirm={() => {
          archive.mutate(undefined, {
            onSuccess: () => {
              setDialog(null);
            },
            onError: fail,
          });
        }}
      />
      <ConfirmDialog
        open={dialog === "unlink"}
        onOpenChange={(open) => {
          setDialog(open ? "unlink" : null);
        }}
        title={t.unlinkTitle(card.display_name)}
        description={t.unlinkText}
        confirmLabel={t.unlinkConfirm}
        loading={unlink.isPending}
        onConfirm={() => {
          unlink.mutate(undefined, {
            onSuccess: () => {
              setDialog(null);
            },
            onError: fail,
          });
        }}
      />
      <InvitationDialog
        target={{ kind: "student", id: card.user_id }}
        name={card.display_name}
        open={dialog === "invite"}
        onOpenChange={(open) => {
          setDialog(open ? "invite" : null);
        }}
      />
    </div>
  );
}

/** «Ученик: карточка» (docs/07 §9.2.3). Вкладки будущих этапов (уроки, ДЗ, прогресс) не созданы. */
export function StudentCardPage() {
  const { id } = useParams();
  const query = useStudent(Number(id));
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
  return <CardView card={query.data} />;
}
