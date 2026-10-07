import { CalendarDays, ChevronLeft, ChevronRight, Repeat } from "lucide-react";
import { useState } from "react";

import { errorMessage } from "@/api/errors";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { PageHeader } from "@/components/common/PageHeader";
import { PageSkeleton } from "@/components/common/PageSkeleton";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import { useMe } from "@/features/auth/api";
import { useStudents } from "@/features/students/api";
import { DEFAULT_TIMEZONE } from "@/features/students/studentForm";
import {
  dayStartUtcIso,
  formatDayKey,
  formatTimeRange,
  localDayKey,
  shiftDayKey,
  todayKey,
  weekDayKeys,
} from "@/lib/datetime";
import { texts } from "@/lib/texts";
import { useBreakpoint } from "@/lib/useBreakpoint";
import { cn } from "@/lib/utils";

import { useLessons } from "./api";
import type { Lesson, LessonStatus } from "./api";
import { LessonDetailDialog } from "./LessonDetailDialog";
import { LessonFormDialog, selectClasses } from "./LessonFormDialog";
import { TemplateFormDialog } from "./TemplateFormDialog";

const t = texts.admin.schedule;
const STUDENTS_FILTER_LIMIT = 200;
const STATUSES: LessonStatus[] = ["scheduled", "completed", "cancelled"];

function subjectLabel(code: string): string {
  return code in texts.admin.subjects
    ? texts.admin.subjects[code as keyof typeof texts.admin.subjects]
    : code;
}

type LessonBlockProps = { lesson: Lesson; timeZone: string; onOpen: (lesson: Lesson) => void };

/** Блок урока: время, предмет, участники; отменённые приглушены (docs/07 §9.2.5). */
function LessonBlock({ lesson, timeZone, onOpen }: LessonBlockProps) {
  const names = lesson.participants.map((p) => p.display_name);
  const people =
    names.length > 2
      ? `${names.slice(0, 2).join(", ")} +${String(names.length - 2)}`
      : names.join(", ");
  return (
    <button
      type="button"
      onClick={() => {
        onOpen(lesson);
      }}
      className={cn(
        "flex w-full flex-col gap-1 rounded-md border border-border bg-card p-3 text-left shadow-card font-body focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        lesson.status === "cancelled" && "opacity-60",
      )}
    >
      <span className="text-sm font-bold">
        {formatTimeRange(lesson.start_at, lesson.end_at, timeZone)}
      </span>
      <span className="text-sm">{subjectLabel(lesson.subject_code)}</span>
      <span className="text-sm text-muted-foreground">{people}</span>
      {lesson.status !== "scheduled" && <StatusBadge status={`lesson.${lesson.status}`} />}
    </button>
  );
}

/** Расписание (docs/07 §9.2.5): список дня на мобильном, колонки недели на десктопе. */
export function SchedulePage() {
  const breakpoint = useBreakpoint();
  const { data: me } = useMe();
  const timeZone = me?.timezone ?? DEFAULT_TIMEZONE;
  const today = todayKey(timeZone);
  const [anchor, setAnchor] = useState(today);
  const [studentId, setStudentId] = useState<number | null>(null);
  const [status, setStatus] = useState<LessonStatus | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [creating, setCreating] = useState<"lesson" | "template" | null>(null);

  const desktop = breakpoint === "desktop";
  const days = weekDayKeys(anchor);
  const weekStart = days[0] ?? anchor;
  const query = useLessons({
    from: dayStartUtcIso(weekStart, timeZone),
    to: dayStartUtcIso(shiftDayKey(weekStart, 7), timeZone),
    studentId,
    status,
  });
  const students = useStudents({ status: "active", q: "", limit: STUDENTS_FILTER_LIMIT });

  const byDay = new Map<string, Lesson[]>();
  for (const lesson of query.data?.items ?? []) {
    const key = localDayKey(lesson.start_at, timeZone);
    byDay.set(key, [...(byDay.get(key) ?? []), lesson]);
  }
  const selected = query.data?.items.find((lesson) => lesson.id === selectedId) ?? null;
  const step = desktop ? 7 : 1;
  const lastDay = days[6] ?? anchor;

  const open = (lesson: Lesson) => {
    setSelectedId(lesson.id);
  };
  const renderDay = (key: string) => {
    const lessons = byDay.get(key) ?? [];
    return lessons.length === 0 ? (
      <p className="text-sm text-muted-foreground font-body">{t.noLessonsDay}</p>
    ) : (
      <ul className="flex flex-col gap-2">
        {lessons.map((lesson) => (
          <li key={lesson.id}>
            <LessonBlock lesson={lesson} timeZone={timeZone} onOpen={open} />
          </li>
        ))}
      </ul>
    );
  };

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
  } else if (query.data.items.length === 0 && desktop) {
    content = <EmptyState icon={CalendarDays} title={t.noLessonsWeek} description={t.emptyHint} />;
  } else if (desktop) {
    content = (
      <div className="grid grid-cols-7 gap-3">
        {days.map((key) => (
          <section key={key} aria-label={formatDayKey(key)} className="flex flex-col gap-2">
            <h2 className={cn("text-sm font-bold font-heading", key === today && "text-primary")}>
              {formatDayKey(key)}
            </h2>
            {renderDay(key)}
          </section>
        ))}
      </div>
    );
  } else {
    content = (
      <div className="flex flex-col gap-3">
        <div className="flex gap-1 overflow-x-auto" role="tablist" aria-label={t.title}>
          {days.map((key) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={key === anchor}
              onClick={() => {
                setAnchor(key);
              }}
              className={cn(
                "min-h-11 shrink-0 rounded-md px-3 text-sm font-semibold font-body",
                key === anchor ? "bg-primary text-primary-foreground" : "bg-muted text-foreground",
              )}
            >
              {formatDayKey(key)}
              {(byDay.get(key)?.length ?? 0) > 0 && (
                <span className="ml-1 text-xs">{byDay.get(key)?.length}</span>
              )}
            </button>
          ))}
        </div>
        {(byDay.get(anchor)?.length ?? 0) === 0 ? (
          <EmptyState
            icon={CalendarDays}
            title={t.noLessonsDay}
            description={query.data.items.length === 0 ? t.emptyHint : undefined}
          />
        ) : (
          renderDay(anchor)
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title={t.title}
        actions={
          <>
            <Button
              variant="outline"
              size="compact"
              onClick={() => {
                setCreating("template");
              }}
            >
              <Repeat className="size-4" aria-hidden />
              {t.newTemplate}
            </Button>
            <Button
              variant="primary"
              onClick={() => {
                setCreating("lesson");
              }}
            >
              {t.newLesson}
            </Button>
          </>
        }
      />
      <div className="flex flex-wrap items-center gap-2">
        <Button
          variant="outline"
          size="compact"
          aria-label={desktop ? t.prevWeek : t.prevDay}
          onClick={() => {
            setAnchor(shiftDayKey(anchor, -step));
          }}
        >
          <ChevronLeft className="size-5" aria-hidden />
        </Button>
        <Button
          variant="outline"
          size="compact"
          onClick={() => {
            setAnchor(today);
          }}
        >
          {t.today}
        </Button>
        <Button
          variant="outline"
          size="compact"
          aria-label={desktop ? t.nextWeek : t.nextDay}
          onClick={() => {
            setAnchor(shiftDayKey(anchor, step));
          }}
        >
          <ChevronRight className="size-5" aria-hidden />
        </Button>
        <p className="text-sm font-semibold font-body">
          {t.weekOf(formatDayKey(weekStart), formatDayKey(lastDay))}
        </p>
      </div>
      <div className="flex flex-col gap-2 md:flex-row">
        <select
          aria-label={t.filterStudent}
          className={cn(selectClasses, "md:max-w-xs")}
          value={studentId === null ? "" : String(studentId)}
          onChange={(event) => {
            setStudentId(event.target.value === "" ? null : Number(event.target.value));
          }}
        >
          <option value="">{t.allStudents}</option>
          {students.data?.items.map((student) => (
            <option key={student.user_id} value={String(student.user_id)}>
              {student.display_name}
            </option>
          ))}
        </select>
        <select
          aria-label={t.filterStatus}
          className={cn(selectClasses, "md:max-w-xs")}
          value={status ?? ""}
          onChange={(event) => {
            const value = STATUSES.find((item) => item === event.target.value);
            setStatus(value ?? null);
          }}
        >
          <option value="">{t.allStatuses}</option>
          {STATUSES.map((item) => (
            <option key={item} value={item}>
              {texts.status[`lesson.${item}`]}
            </option>
          ))}
        </select>
      </div>
      {content}
      {creating === "lesson" && (
        <LessonFormDialog
          open
          onOpenChange={(next) => {
            if (!next) setCreating(null);
          }}
          defaultDate={anchor}
          timeZone={timeZone}
        />
      )}
      {creating === "template" && (
        <TemplateFormDialog
          open
          onOpenChange={(next) => {
            if (!next) setCreating(null);
          }}
          todayKey={today}
          timeZone={timeZone}
        />
      )}
      <LessonDetailDialog
        key={selectedId ?? "none"}
        lesson={selected}
        timeZone={timeZone}
        onClose={() => {
          setSelectedId(null);
        }}
      />
    </div>
  );
}
