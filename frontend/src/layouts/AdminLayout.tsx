import { LogOut } from "lucide-react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { OfflineBanner } from "@/components/common/OfflineBanner";
import { useLogout, useMe } from "@/features/auth/api";
import { texts } from "@/lib/texts";
import { useBreakpoint } from "@/lib/useBreakpoint";
import { cn } from "@/lib/utils";

import { ADMIN_SIDEBAR_NAV, ADMIN_TAB_NAV } from "./navigation";
import type { NavItem } from "./navigation";
import { TabBar } from "./TabBar";

type SidebarProps = {
  items: readonly NavItem[];
  /** Планшет: компактное меню только с иконками. */
  compact: boolean;
};

/** Боковое меню десктопа и планшета (docs/07 §7.2): фон brand-black, активный пункт — полоска слева. */
function Sidebar({ items, compact }: SidebarProps) {
  const logout = useLogout();
  const navigate = useNavigate();
  return (
    <aside
      className={cn(
        "sticky top-0 flex h-dvh shrink-0 flex-col bg-brand-black py-4 text-brand-white",
        compact ? "w-16" : "w-60",
      )}
    >
      <p
        className={cn(
          "mb-6 px-4 text-sm font-extrabold uppercase tracking-tight font-display",
          compact && "sr-only",
        )}
      >
        <span className="text-brand-white">{texts.common.brandFirst}</span>{" "}
        <span className="text-brand-green-light">{texts.common.brandSecond}</span>
      </p>
      <nav aria-label={texts.common.mainNavigation} className="flex-1">
        <ul className="flex flex-col gap-1">
          {items.map(({ to, label, icon: Icon }) => (
            <li key={to}>
              <NavLink
                to={to}
                aria-label={compact ? label : undefined}
                title={compact ? label : undefined}
                className={({ isActive }) =>
                  cn(
                    "flex min-h-11 items-center gap-3 border-l-4 px-4 text-sm font-semibold font-body focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring",
                    compact && "justify-center px-0",
                    isActive
                      ? "border-brand-green-light bg-brand-white/10 text-brand-white"
                      : "border-transparent text-gray-200 hover:bg-brand-white/5",
                  )
                }
              >
                <Icon className="size-5 shrink-0" strokeWidth={1.75} aria-hidden />
                {!compact && <span>{label}</span>}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
      <button
        type="button"
        aria-label={compact ? texts.common.logout : undefined}
        disabled={logout.isPending}
        onClick={() => {
          logout.mutate(undefined, {
            onSuccess: () => {
              void navigate("/login", { replace: true });
            },
          });
        }}
        className={cn(
          "flex min-h-11 items-center gap-3 px-4 text-sm font-semibold text-gray-200 font-body hover:bg-brand-white/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring",
          compact && "justify-center px-0",
        )}
      >
        <LogOut className="size-5 shrink-0" strokeWidth={1.75} aria-hidden />
        {!compact && <span>{texts.common.logout}</span>}
      </button>
    </aside>
  );
}

/**
 * Каркас Admin App (docs/07 §7.2): на мобильном — нижний таб-бар из пяти пунктов,
 * на планшете (768–1023) — компактное меню с иконками, на десктопе (от 1024) — боковое меню 240 px.
 * Пункты «Финансы» и «Сотрудники» видны только владельцу (права всё равно проверяет сервер).
 */
export function AdminLayout() {
  const breakpoint = useBreakpoint();
  const { data: me } = useMe();
  const isOwner = me?.role === "owner";
  const sidebarItems = ADMIN_SIDEBAR_NAV.filter((item) => item.ownerOnly !== true || isOwner);

  if (breakpoint === "mobile") {
    return (
      <div className="flex min-h-dvh flex-col bg-background">
        <OfflineBanner />
        <main className="flex-1 px-4 py-4">
          <Outlet />
        </main>
        <TabBar items={ADMIN_TAB_NAV} />
      </div>
    );
  }
  return (
    <div className="flex min-h-dvh bg-background">
      <Sidebar items={sidebarItems} compact={breakpoint === "tablet"} />
      <div className="flex min-w-0 flex-1 flex-col">
        <OfflineBanner />
        <main className="flex-1 px-6 py-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
