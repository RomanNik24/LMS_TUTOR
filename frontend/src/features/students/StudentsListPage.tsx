import { Search, Users } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { errorMessage } from "@/api/errors";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { PageHeader } from "@/components/common/PageHeader";
import { PageSkeleton } from "@/components/common/PageSkeleton";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useBreakpoint } from "@/lib/useBreakpoint";
import { texts } from "@/lib/texts";
import { useSubjectName } from "@/features/reference/api";

import { PAGE_SIZE, useStudents } from "./api";
import type { StudentListItem, StudentStatus } from "./api";

const t = texts.admin.students;

function Flags({ student }: { student: StudentListItem }) {
  return (
    <span className="flex flex-wrap items-center gap-1.5">
      {!student.is_active && (
        <span className="text-xs font-semibold text-muted-foreground font-body">
          {t.archivedBadge}
        </span>
      )}
      {student.bot_blocked && <StatusBadge status="bot.blocked" />}
      {student.invite_pending && student.is_active && (
        <span className="text-xs font-semibold text-warning-fg font-body">{t.invitePending}</span>
      )}
    </span>
  );
}

function meta(student: StudentListItem, subjectLabel: (code: string) => string): string {
  const parts: string[] = [];
  if (student.school_class !== null) parts.push(t.classLabel(student.school_class));
  if (student.subjects.length > 0) parts.push(student.subjects.map(subjectLabel).join(", "));
  return parts.join(" · ");
}

function StudentCards({ items }: { items: StudentListItem[] }) {
  const subjectLabel = useSubjectName();
  return (
    <ul className="flex flex-col gap-3">
      {items.map((student) => (
        <li key={student.user_id}>
          <Link
            to={`/admin/students/${String(student.user_id)}`}
            className="block rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <Card className="flex flex-col gap-1.5">
              <span className="text-base font-bold font-heading">{student.display_name}</span>
              <span className="text-sm text-muted-foreground font-body">
                {meta(student, subjectLabel)}
              </span>
              <Flags student={student} />
            </Card>
          </Link>
        </li>
      ))}
    </ul>
  );
}

function StudentTable({ items }: { items: StudentListItem[] }) {
  const subjectLabel = useSubjectName();
  return (
    <table className="w-full border-collapse text-left font-body">
      <thead>
        <tr className="border-b border-border text-sm text-muted-foreground">
          <th className="py-2 pr-4 font-medium">{texts.admin.students.form.name}</th>
          <th className="py-2 pr-4 font-medium">{texts.admin.students.form.schoolClass}</th>
          <th className="py-2 pr-4 font-medium">{texts.admin.students.form.subjects}</th>
          <th className="py-2 font-medium" />
        </tr>
      </thead>
      <tbody>
        {items.map((student) => (
          <tr key={student.user_id} className="border-b border-border">
            <td className="py-3 pr-4">
              <Link
                to={`/admin/students/${String(student.user_id)}`}
                className="font-semibold text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                {student.display_name}
              </Link>
            </td>
            <td className="py-3 pr-4">
              {student.school_class === null ? "—" : String(student.school_class)}
            </td>
            <td className="py-3 pr-4">{student.subjects.map(subjectLabel).join(", ") || "—"}</td>
            <td className="py-3">
              <Flags student={student} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** «Ученики: список» (docs/07 §9.2.2): поиск, «Активные / Архив», карточки на мобильном, таблица на десктопе. */
export function StudentsListPage() {
  const breakpoint = useBreakpoint();
  const [status, setStatus] = useState<StudentStatus>("active");
  const [search, setSearch] = useState("");
  const [limit, setLimit] = useState(PAGE_SIZE);
  const query = useStudents({ status, q: search, limit });

  const actions = (
    <Button asChild variant="primary">
      <Link to="/admin/students/new">{t.newStudent}</Link>
    </Button>
  );

  let content;
  if (query.isPending) {
    content = <PageSkeleton />;
  } else if (query.isError) {
    content = (
      <ErrorState
        message={errorMessage(query.error)}
        onRetry={() => {
          void query.refetch();
        }}
      />
    );
  } else if (query.data.items.length === 0) {
    const searching = search.trim() !== "";
    content =
      status === "active" && !searching ? (
        <EmptyState
          icon={Users}
          title={texts.empty.adminStudents.title}
          description={texts.empty.adminStudents.text}
          action={actions}
        />
      ) : (
        <EmptyState icon={Users} title={searching ? t.noResults : t.noArchived} />
      );
  } else {
    const { items, total } = query.data;
    content = (
      <>
        {breakpoint === "desktop" ? <StudentTable items={items} /> : <StudentCards items={items} />}
        {items.length < total && (
          <Button
            variant="outline"
            onClick={() => {
              setLimit((current) => current + PAGE_SIZE);
            }}
          >
            {t.loadMore}
          </Button>
        )}
      </>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={texts.nav.admin.students} actions={actions} />
      <div className="flex flex-col gap-3 md:flex-row md:items-center">
        <div className="relative md:max-w-sm md:flex-1">
          <Search
            className="pointer-events-none absolute left-3 top-1/2 size-5 -translate-y-1/2 text-muted-foreground"
            aria-hidden
          />
          <Input
            type="search"
            aria-label={t.search}
            placeholder={t.search}
            className="pl-10"
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
              setLimit(PAGE_SIZE);
            }}
          />
        </div>
        <Tabs
          value={status}
          onValueChange={(value) => {
            setStatus(value === "archived" ? "archived" : "active");
            setLimit(PAGE_SIZE);
          }}
        >
          <TabsList>
            <TabsTrigger value="active">{t.filterActive}</TabsTrigger>
            <TabsTrigger value="archived">{t.filterArchived}</TabsTrigger>
          </TabsList>
        </Tabs>
      </div>
      {content}
    </div>
  );
}
