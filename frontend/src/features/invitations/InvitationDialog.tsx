import { Copy, Share2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { errorMessage } from "@/api/errors";
import { ErrorState } from "@/components/common/ErrorState";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { texts } from "@/lib/texts";

import { useIssueInvitation, useRevokeInvitation } from "./api";
import type { InviteTarget } from "./api";

const t = texts.admin.invitation;
const TELEGRAM_SHARE_URL = "https://t.me/share/url";

type InvitationDialogProps = {
  target: InviteTarget;
  /** Для кого приглашение (показывается в заголовке). */
  name: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

function formatExpires(iso: string): string {
  return new Intl.DateTimeFormat("ru-RU", { dateStyle: "long" }).format(new Date(iso));
}

/**
 * Экран приглашения (docs/07 §9.2.4): ссылка t.me, «Скопировать», «Поделиться», срок 7 дней,
 * «Откроется один раз», «Перевыпустить», «Отозвать». Ссылка выпускается при открытии окна
 * и нигде не сохраняется: после закрытия её можно только выпустить заново.
 */
export function InvitationDialog({ target, name, open, onOpenChange }: InvitationDialogProps) {
  const issue = useIssueInvitation(target);
  const revoke = useRevokeInvitation();
  const [revoked, setRevoked] = useState(false);
  const started = useRef(false);

  const { mutate: issueInvite, reset: resetIssue } = issue;
  useEffect(() => {
    if (!open) {
      started.current = false;
      setRevoked(false);
      resetIssue();
      return;
    }
    if (!started.current) {
      started.current = true;
      issueInvite();
    }
  }, [open, issueInvite, resetIssue]);

  const invitation = issue.data;

  async function copy(url: string) {
    try {
      await navigator.clipboard.writeText(url);
      toast.success(t.copied);
    } catch {
      toast.error(t.copyFailed);
    }
  }

  function share(url: string) {
    const link = `${TELEGRAM_SHARE_URL}?url=${encodeURIComponent(url)}&text=${encodeURIComponent(t.shareText)}`;
    window.open(link, "_blank", "noopener,noreferrer");
  }

  function reissue() {
    setRevoked(false);
    issueInvite();
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="text-lg font-bold font-heading">
            {t.title}: {name}
          </DialogTitle>
          <DialogDescription className="text-sm text-muted-foreground font-body">
            {t.hint}
          </DialogDescription>
        </DialogHeader>
        {issue.isPending && (
          <div role="status" aria-label={t.preparing}>
            <Skeleton className="h-12 w-full" />
          </div>
        )}
        {issue.isError && <ErrorState message={errorMessage(issue.error)} onRetry={reissue} />}
        {invitation !== undefined && !revoked && (
          <div className="flex flex-col gap-3">
            <Input
              readOnly
              aria-label={t.title}
              value={invitation.url}
              onFocus={(event) => {
                event.currentTarget.select();
              }}
            />
            <p className="text-sm text-muted-foreground font-body">
              {t.expires(formatExpires(invitation.expires_at))}
            </p>
            <div className="flex flex-wrap gap-2">
              <Button
                variant="primary"
                onClick={() => {
                  void copy(invitation.url);
                }}
              >
                <Copy className="size-4" aria-hidden />
                {t.copy}
              </Button>
              <Button
                variant="outline"
                onClick={() => {
                  share(invitation.url);
                }}
              >
                <Share2 className="size-4" aria-hidden />
                {t.share}
              </Button>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button variant="ghost" size="compact" loading={issue.isPending} onClick={reissue}>
                {t.reissue}
              </Button>
              <Button
                variant="ghost"
                size="compact"
                loading={revoke.isPending}
                onClick={() => {
                  revoke.mutate(invitation.id, {
                    onSuccess: () => {
                      setRevoked(true);
                      toast.success(t.revoked);
                    },
                    onError: (error) => {
                      toast.error(errorMessage(error));
                    },
                  });
                }}
              >
                {t.revoke}
              </Button>
            </div>
          </div>
        )}
        {revoked && (
          <div className="flex flex-col gap-3">
            <p className="text-sm text-muted-foreground font-body">{t.revoked}</p>
            <Button variant="outline" onClick={reissue}>
              {t.reissue}
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
