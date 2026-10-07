import { Outlet } from "react-router-dom";

import { AppHeader } from "./AppHeader";
import { STUDENT_NAV } from "./navigation";
import { TabBar } from "./TabBar";

/**
 * Каркас Student App (docs/07 §7.1): шапка, контент, нижний таб-бар из трёх пунктов.
 * На десктопе контент — колонка до 560 px по центру, таб-бар остаётся внизу колонки.
 */
export function StudentLayout() {
  return (
    <div className="min-h-dvh bg-background">
      <div className="mx-auto flex min-h-dvh w-full max-w-[560px] flex-col bg-background">
        <AppHeader />
        <main className="flex-1 px-4 py-4">
          <Outlet />
        </main>
        <TabBar items={STUDENT_NAV} />
      </div>
    </div>
  );
}
