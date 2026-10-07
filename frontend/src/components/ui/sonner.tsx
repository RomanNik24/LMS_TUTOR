import { Toaster as SonnerToaster } from "sonner";

/**
 * Тосты (docs/07 §6.14): снизу на мобильном, сверху справа на десктопе; успех — primary,
 * ошибка — destructive; 3–4 секунды. Вызов — `toast.success(...)` из пакета sonner.
 */
export function Toaster() {
  return (
    <SonnerToaster
      position="bottom-center"
      duration={3500}
      toastOptions={{
        classNames: {
          toast: "rounded-md font-body shadow-overlay",
          success: "!bg-primary !text-primary-foreground !border-transparent",
          error: "!bg-destructive !text-destructive-foreground !border-transparent",
        },
      }}
    />
  );
}
