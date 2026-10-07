import {
  BookOpen,
  CalendarDays,
  ClipboardCheck,
  ClipboardList,
  LineChart,
  Menu,
  Sun,
  UserCog,
  Users,
  Wallet,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { texts } from "@/lib/texts";

/** Пункт навигации: путь, подпись, иконка и (для админки) видимость по ролям. */
export type NavItem = {
  to: string;
  label: string;
  icon: LucideIcon;
  /** Пункт виден только владельцу. */
  ownerOnly?: boolean;
};

/** Student App: нижний таб-бар из трёх пунктов (docs/07 §7.1). */
export const STUDENT_NAV: readonly NavItem[] = [
  { to: "/app/schedule", label: texts.nav.student.schedule, icon: CalendarDays },
  { to: "/app/homework", label: texts.nav.student.homework, icon: ClipboardList },
  { to: "/app/reports", label: texts.nav.student.reports, icon: LineChart },
];

/** Admin App, мобильный таб-бар из пяти пунктов (docs/07 §7.2). */
export const ADMIN_TAB_NAV: readonly NavItem[] = [
  { to: "/admin/today", label: texts.nav.admin.today, icon: Sun },
  { to: "/admin/schedule", label: texts.nav.admin.schedule, icon: CalendarDays },
  { to: "/admin/homework", label: texts.nav.admin.homework, icon: ClipboardList },
  { to: "/admin/students", label: texts.nav.admin.students, icon: Users },
  { to: "/admin/more", label: texts.nav.admin.more, icon: Menu },
];

/** Пункты раздела «Ещё» на мобильном и дополнение бокового меню на десктопе. */
export const ADMIN_MORE_NAV: readonly NavItem[] = [
  { to: "/admin/exams", label: texts.nav.admin.exams, icon: ClipboardCheck },
  { to: "/admin/catalog", label: texts.nav.admin.catalog, icon: BookOpen },
  { to: "/admin/finance", label: texts.nav.admin.finance, icon: Wallet, ownerOnly: true },
  { to: "/admin/staff", label: texts.nav.admin.staff, icon: UserCog, ownerOnly: true },
];

/** Боковое меню десктопа: все основные разделы без «Ещё» плюс содержимое «Ещё». */
export const ADMIN_SIDEBAR_NAV: readonly NavItem[] = [
  ...ADMIN_TAB_NAV.filter((item) => item.to !== "/admin/more"),
  ...ADMIN_MORE_NAV,
];
