import { WifiOff } from "lucide-react";
import { useSyncExternalStore } from "react";

import { texts } from "@/lib/texts";

function subscribe(onChange: () => void): () => void {
  window.addEventListener("online", onChange);
  window.addEventListener("offline", onChange);
  return () => {
    window.removeEventListener("online", onChange);
    window.removeEventListener("offline", onChange);
  };
}

/** Есть ли соединение по данным браузера (`navigator.onLine`). */
export function useOnline(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => navigator.onLine,
    () => true,
  );
}

/** Плашка «Нет соединения» над содержимым; пока связи нет, экраны показывают ошибку и «Повторить». */
export function OfflineBanner() {
  const online = useOnline();
  if (online) return null;
  return (
    <div
      role="status"
      className="flex items-center gap-2 bg-warning-bg px-4 py-2 text-sm font-semibold text-warning-fg font-body"
    >
      <WifiOff className="size-5 shrink-0" strokeWidth={1.75} aria-hidden />
      {texts.messages.offlineBanner}
    </div>
  );
}
