import { Slot } from "@radix-ui/react-slot";
import { cva } from "class-variance-authority";
import type { VariantProps } from "class-variance-authority";
import { Loader2 } from "lucide-react";
import type { ButtonHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

/**
 * Кнопки по docs/07 §6.1: высота 48, радиус 12, фокус-кольцо 2 px, disabled 45%.
 * Правило одного главного действия: на экране одна primary или highlight.
 */
export const buttonVariants = cva(
  "inline-flex min-h-12 items-center justify-center gap-2 rounded-md px-5 text-base font-semibold font-body transition-[filter,background-color] duration-150 ease-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:pointer-events-none disabled:opacity-45 motion-reduce:transition-none",
  {
    variants: {
      variant: {
        primary: "bg-primary text-primary-foreground hover:brightness-90 active:brightness-85",
        highlight:
          "bg-highlight text-highlight-foreground hover:brightness-90 active:brightness-85",
        secondary:
          "bg-secondary text-secondary-foreground hover:brightness-95 active:brightness-90",
        outline: "border border-border bg-transparent text-foreground hover:bg-muted",
        ghost: "bg-transparent text-foreground hover:bg-muted",
        destructive:
          "bg-destructive text-destructive-foreground hover:brightness-90 active:brightness-85",
      },
      size: {
        default: "",
        compact: "min-h-11 px-3 text-sm",
      },
    },
    defaultVariants: { variant: "primary", size: "default" },
  },
);

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> &
  VariantProps<typeof buttonVariants> & {
    /** Показывает спиннер вместо иконки и блокирует кнопку (идёт отправка). */
    loading?: boolean;
    /** Отрисовать кнопку как дочерний элемент (например, ссылку `<a>`). */
    asChild?: boolean;
  };

export function Button({
  variant,
  size,
  loading = false,
  asChild = false,
  disabled,
  className,
  children,
  type = "button",
  ...props
}: ButtonProps) {
  const classes = cn(buttonVariants({ variant, size }), className);
  if (asChild) {
    return (
      <Slot className={classes} {...props}>
        {children}
      </Slot>
    );
  }
  return (
    <button
      type={type}
      className={classes}
      disabled={disabled === true || loading}
      aria-busy={loading || undefined}
      {...props}
    >
      {loading && (
        <Loader2 className="size-5 animate-spin motion-reduce:animate-none" aria-hidden />
      )}
      {children}
    </button>
  );
}
