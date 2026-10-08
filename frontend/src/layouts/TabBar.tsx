import { NavLink } from "react-router-dom";

import { texts } from "@/lib/texts";
import { cn } from "@/lib/utils";

import type { NavItem } from "./navigation";

type TabBarProps = {
  items: readonly NavItem[];
};

/**
 * Нижний таб-бар (docs/07 §7.1): высота 64 + safe-area, фон card, верхняя граница;
 * активный пункт — primary с индикатором 3×24 сверху, неактивный — gray-600.
 */
export function TabBar({ items }: TabBarProps) {
  return (
    <nav
      aria-label={texts.common.mainNavigation}
      className="sticky bottom-0 z-30 border-t border-border bg-card pb-[env(safe-area-inset-bottom)]"
    >
      <ul className="flex h-16">
        {items.map(({ to, label, icon: Icon }) => (
          <li key={to} className="flex-1">
            <NavLink
              to={to}
              className={({ isActive }) =>
                cn(
                  "relative flex h-full min-h-11 flex-col items-center justify-center gap-1 text-xs font-semibold font-body focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring",
                  isActive ? "text-primary" : "text-muted-foreground",
                )
              }
            >
              {({ isActive }) => (
                <>
                  {isActive && (
                    <span
                      aria-hidden
                      className="absolute top-0 h-[3px] w-6 rounded-b-sm bg-primary"
                    />
                  )}
                  <Icon className="size-6" strokeWidth={1.75} aria-hidden />
                  <span>{label}</span>
                </>
              )}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}
