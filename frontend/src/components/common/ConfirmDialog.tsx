import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { texts } from "@/lib/texts";

type ConfirmDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Заголовок с последствием («Отменить урок 14 окт, 17:00?»). */
  title: string;
  description?: string;
  /** Глагол опасного действия на кнопке («Отменить урок»). */
  confirmLabel: string;
  onConfirm: () => void;
  loading?: boolean;
};

/** Подтверждение опасного действия (docs/07 §6.14): «Назад» (outline) и destructive с глаголом. */
export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  onConfirm,
  loading = false,
}: ConfirmDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="text-lg font-bold font-heading">{title}</DialogTitle>
          {description !== undefined && (
            <DialogDescription className="text-sm text-muted-foreground font-body">
              {description}
            </DialogDescription>
          )}
        </DialogHeader>
        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => {
              onOpenChange(false);
            }}
          >
            {texts.common.back}
          </Button>
          <Button variant="destructive" loading={loading} onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
