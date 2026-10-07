import { useSyncExternalStore } from "react";

/** Границы адаптивности (docs/07 §7.2): планшет от 768, десктоп от 1024. */
const TABLET_QUERY = "(min-width: 768px)";
const DESKTOP_QUERY = "(min-width: 1024px)";

export type Breakpoint = "mobile" | "tablet" | "desktop";

function subscribe(onChange: () => void): () => void {
  const lists = [window.matchMedia(TABLET_QUERY), window.matchMedia(DESKTOP_QUERY)];
  for (const list of lists) {
    list.addEventListener("change", onChange);
  }
  return () => {
    for (const list of lists) {
      list.removeEventListener("change", onChange);
    }
  };
}

function snapshot(): Breakpoint {
  if (window.matchMedia(DESKTOP_QUERY).matches) {
    return "desktop";
  }
  return window.matchMedia(TABLET_QUERY).matches ? "tablet" : "mobile";
}

/** Текущая ширина экрана: мобильная вёрстка, планшет или десктоп. */
export function useBreakpoint(): Breakpoint {
  return useSyncExternalStore(subscribe, snapshot, () => "mobile");
}
