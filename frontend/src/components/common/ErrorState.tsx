import { texts } from "@/lib/texts";

type ErrorStateProps = {
  message: string;
  onRetry?: () => void;
};

/** Сообщение об ошибке с необязательной кнопкой повтора. */
export function ErrorState({ message, onRetry }: ErrorStateProps) {
  return (
    <div className="flex flex-col items-center gap-4 px-4 text-center" role="alert">
      <p className="text-base text-foreground font-body">{message}</p>
      {onRetry !== undefined && (
        <button
          type="button"
          onClick={onRetry}
          className="min-h-11 rounded-md bg-primary px-5 text-primary-foreground font-body"
        >
          {texts.login.retry}
        </button>
      )}
    </div>
  );
}
