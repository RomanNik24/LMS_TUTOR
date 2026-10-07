import { useId } from "react";
import type { InputHTMLAttributes, ReactNode } from "react";

import { cn } from "@/lib/utils";

type InputProps = InputHTMLAttributes<HTMLInputElement> & {
  invalid?: boolean;
};

/** Поле ввода по docs/07 §6.2: высота 48, радиус 12, граница input, фокус — primary и кольцо. */
export function Input({ className, invalid = false, ...props }: InputProps) {
  return (
    <input
      aria-invalid={invalid || undefined}
      className={cn(
        "min-h-12 w-full rounded-md border bg-card px-4 text-base text-foreground font-body placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        invalid
          ? "border-destructive focus-visible:border-destructive"
          : "border-input focus-visible:border-primary",
        className,
      )}
      {...props}
    />
  );
}

type FieldProps = {
  label: string;
  error?: string;
  hint?: string;
  children: (props: { id: string; invalid: boolean; describedBy: string | undefined }) => ReactNode;
};

/** Подпись (Inter 14, вес 500) над полем и текст ошибки под ним; связь через aria. */
export function Field({ label, error, hint, children }: FieldProps) {
  const id = useId();
  const messageId = `${id}-message`;
  const hasMessage = error !== undefined || hint !== undefined;
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-medium text-foreground font-body">
        {label}
      </label>
      {children({
        id,
        invalid: error !== undefined,
        describedBy: hasMessage ? messageId : undefined,
      })}
      {hasMessage && (
        <p
          id={messageId}
          role={error !== undefined ? "alert" : undefined}
          className={cn(
            "text-sm font-body",
            error !== undefined ? "text-destructive" : "text-muted-foreground",
          )}
        >
          {error ?? hint}
        </p>
      )}
    </div>
  );
}
