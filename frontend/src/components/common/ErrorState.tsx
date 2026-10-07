import { AlertTriangle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { texts } from "@/lib/texts";

type ErrorStateProps = {
  message: string;
  onRetry?: () => void;
};

/** Ошибка (docs/07 §6.16): иконка-предупреждение, понятный текст, кнопка «Повторить». */
export function ErrorState({ message, onRetry }: ErrorStateProps) {
  return (
    <div className="flex flex-col items-center gap-4 px-4 text-center" role="alert">
      <AlertTriangle className="size-10 text-destructive" strokeWidth={1.75} aria-hidden />
      <p className="text-base text-foreground font-body">{message}</p>
      {onRetry !== undefined && (
        <Button variant="primary" onClick={onRetry}>
          {texts.login.retry}
        </Button>
      )}
    </div>
  );
}
