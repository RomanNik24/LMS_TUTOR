import { ChevronRight, LogOut } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";

import { PageHeader } from "@/components/common/PageHeader";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useLogout, useMe } from "@/features/auth/api";
import { ADMIN_MORE_NAV } from "@/layouts/navigation";
import { texts } from "@/lib/texts";

/** Раздел «Ещё» мобильной админки (docs/07 §7.2): Пробники, Каталог, Финансы, Сотрудники, Выход. */
export function MorePage() {
  const { data: me } = useMe();
  const logout = useLogout();
  const navigate = useNavigate();
  const items = ADMIN_MORE_NAV.filter((item) => item.ownerOnly !== true || me?.role === "owner");
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={texts.nav.admin.more} />
      <ul className="flex flex-col gap-2">
        {items.map(({ to, label, icon: Icon }) => (
          <li key={to}>
            <Link
              to={to}
              className="block rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <Card className="flex min-h-12 items-center gap-3">
                <Icon className="size-5 text-primary" strokeWidth={1.75} aria-hidden />
                <span className="flex-1 text-base font-semibold font-body">{label}</span>
                <ChevronRight className="size-5 text-gray-600" aria-hidden />
              </Card>
            </Link>
          </li>
        ))}
      </ul>
      <Button
        variant="outline"
        loading={logout.isPending}
        onClick={() => {
          logout.mutate(undefined, {
            onSuccess: () => {
              void navigate("/login", { replace: true });
            },
          });
        }}
      >
        <LogOut className="size-5" aria-hidden />
        {texts.common.logout}
      </Button>
    </div>
  );
}
