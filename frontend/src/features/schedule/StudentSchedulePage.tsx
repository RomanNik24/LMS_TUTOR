import { CalendarDays, ChevronLeft, ChevronRight, ExternalLink } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { errorMessage } from "@/api/errors";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { PageSkeleton } from "@/components/common/PageSkeleton";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useMe } from "@/features/auth/api";
import { DEFAULT_TIMEZONE } from "@/features/students/studentForm";
import {
  dayStartUtcIso,
  formatDayKey,
  formatDayKeyLong,
  formatTimeRange,
  localDayKey,
  minutesUntil,
  shiftDayKey,
  todayKey,
  weekDayKeys,
} from "@/lib/datetime";
import { texts } from "@/lib/texts";
import { cn } from "@/lib/utils";

import { useStudentLessons } from "./studentApi";
import type { StudentLesson } from "./studentApi";

const t = texts.student.schedule;
const LIST_DAYS = 28;

function subjectLabel(code: string): string {
  return code in texts.admin.subjects
    ? texts.admin.subjects[code as keyof typeof texts.admin.subjects]
    : code;
}

function capitalize(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

/** Заголовок дня: «Сегодня», «Завтра», «Среда, 16 октября». */
function dayHeading(key: string, today: string): string {
  if (key === today) return t.today;
  if (key === shiftDayKey(today, 1)) return t.tomorrow;
  return capitalize(formatDayKeyLong(key));
}

function group(lessons: StudentLesson[], timeZone: string): [string, StudentLesson[]][] {
  const byDay = new Map<string, StudentLesson[]>();
  for (const lesson of lessons) {
    const key = localDayKey(lesson.start_at, timeZone);
    byDay.set(key, [...(byDay.get(key) ?? []), lesson]);
  }
  return [...byDay.entries()].sort(([a], [b]) => a.localeCompare(b));
}

function LessonCard({ lesson, timeZone }: { lesson: StudentLesson; timeZone: string }) {
  return (
    <Link
      to={`/app/schedule/${String(lesson.id)}`}
      className={cn(
        "flex flex-col gap-1 rounded-md border border-border bg-card p-4 shadow-card font-body focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        lesson.status === "cancelled" && "opacity-60",
      )}
    >
      <span className="text-base font-extrabold font-display">
        {formatTimeRange(lesson.start_at, lesson.end_at, timeZone)}
      </span>
      <span className="text-sm">{subjectLabel(lesson.subject_code)}</span>
      {lesson.topic !== null && (
        <span className="text-sm text-muted-foreground">{lesson.topic}</span>
      )}
      {lesson.status !== "scheduled" && <StatusBadge status={`lesson.${lesson.status}`} />}
    </Link>
  );
}

function Hero({
  name,
  next,
  timeZone,
}: {
  name: string;
  next: StudentLesson | undefined;
  timeZone: string;
}) {
  return (
    <section className="-mx-4 -mt-4 flex flex-col gap-4 bg-[image:var(--hero-gradient)] px-4 pb-6 pt-5 text-hero-foreground">
      <h1 className="text-xl font-extrabold font-heading">
        {texts.hello.greeting.replace("{name}", name)}
      </h1>
      {next !== undefined && (
        <div className="flex flex-col gap-2 rounded-lg bg-card p-4 text-card-foreground shadow-card">
          <p className="text-xs font-semibold uppercase text-muted-foreground font-body">
            {t.nextLesson}
          </p>
          <p className="text-2xl font-extrabold font-display">
            {formatTimeRange(next.start_at, next.end_at, timeZone)}
          </p>
          <p className="text-sm font-body">
            {subjectLabel(next.subject_code)} · {t.until(minutesUntil(next.start_at))}
          </p>
          {next.video_url !== null && (
            <Button asChild variant="highlight">
              <a href={next.video_url} target="_blank" rel="noopener noreferrer">
                <ExternalLink className="size-4" aria-hidden />
                {t.card.video}
              </a>
            </Button>
          )}
        </div>
      )}
    </section>
  );
}

function ListView({
  lessons,
  timeZone,
  today,
}: {
  lessons: StudentLesson[];
  timeZone: string;
  today: string;
}) {
  if (lessons.length === 0) {
    return (
      <EmptyState
        icon={CalendarDays}
        title={texts.empty.studentSchedule.title}
        description={texts.empty.studentSchedule.text}
      />
    );
  }
  return (
    <div className="flex flex-col gap-5">
      {group(lessons, timeZone).map(([key, items]) => (
        <section key={key} className="flex flex-col gap-2">
          <h2 className="text-sm font-semibold text-gray-600 font-body">
            {dayHeading(key, today)}
          </h2>
          {items.map((lesson) => (
            <LessonCard key={lesson.id} lesson={lesson} timeZone={timeZone} />
          ))}
        </section>
      ))}
    </div>
  );
}

function WeekView({ timeZone, today }: { timeZone: string; today: string }) {
  const [anchor, setAnchor] = useState(today);
  const days = weekDayKeys(anchor);
  const first = days[0] ?? anchor;
  const last = days[6] ?? anchor;
  const query = useStudentLessons(
    dayStartUtcIso(first, timeZone),
    dayStartUtcIso(shiftDayKey(first, 7), timeZone),
  );
  const grouped = new Map(group(query.data ?? [], timeZone));
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <Button
          variant="outline"
          size="compact"
          aria-label={t.prevWeek}
          onClick={() => {
            setAnchor(shiftDayKey(anchor, -7));
          }}
        >
          <ChevronLeft className="size-5" aria-hidden />
        </Button>
        <button
          type="button"
          className="min-h-11 text-sm font-semibold font-body"
          onClick={() => {
            setAnchor(today);
          }}
        >
          {formatDayKey(first)} — {formatDayKey(last)}
        </button>
        <Button
          variant="outline"
          size="compact"
          aria-label={t.nextWeek}
          onClick={() => {
            setAnchor(shiftDayKey(anchor, 7));
          }}
        >
          <ChevronRight className="size-5" aria-hidden />
        </Button>
      </div>
      {query.isPending && <PageSkeleton cards={2} />}
      {query.isError && (
        <ErrorState
          message={errorMessage(query.error)}
          onRetry={() => {
            void query.refetch();
          }}
        />
      )}
      {query.data !== undefined && (
        <div className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-2">
          {days.map((key) => (
            <section
              key={key}
              aria-label={formatDayKey(key)}
              className={cn(
                "flex min-w-[8.5rem] flex-1 flex-col gap-2 rounded-md p-2",
                key === today ? "bg-success-bg" : "bg-muted",
              )}
            >
              <h2 className="text-xs font-bold font-heading">{formatDayKey(key)}</h2>
              {(grouped.get(key) ?? []).map((lesson) => (
                <Link
                  key={lesson.id}
                  to={`/app/schedule/${String(lesson.id)}`}
                  className={cn(
                    "rounded-sm bg-card p-2 text-xs font-body shadow-card focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                    lesson.status === "cancelled" && "opacity-60",
                  )}
                >
                  <span className="block font-bold">
                    {formatTimeRange(lesson.start_at, lesson.end_at, timeZone)}
                  </span>
                  {subjectLabel(lesson.subject_code)}
                </Link>
              ))}
            </section>
          ))}
        </div>
      )}
      {query.data?.length === 0 && (
        <p className="text-sm text-muted-foreground font-body">{t.noLessonsWeek}</p>
      )}
    </div>
  );
}

/** Расписание ученика (docs/07 §9.1.1–9.1.2): герой с ближайшим уроком, список по дням, неделя. */
export function StudentSchedulePage() {
  const { data: me } = useMe();
  const timeZone = me?.timezone ?? DEFAULT_TIMEZONE;
  const today = todayKey(timeZone);
  const query = useStudentLessons(
    dayStartUtcIso(today, timeZone),
    dayStartUtcIso(shiftDayKey(today, LIST_DAYS), timeZone),
  );
  const upcoming = (query.data ?? []).filter((lesson) => lesson.status === "scheduled");
  const next = upcoming.find((lesson) => minutesUntil(lesson.end_at) > 0);

  return (
    <div className="flex flex-col gap-4">
      <Hero name={me?.display_name ?? ""} next={next} timeZone={timeZone} />
      <Tabs defaultValue="list">
        <TabsList>
          <TabsTrigger value="list">{t.list}</TabsTrigger>
          <TabsTrigger value="week">{t.week}</TabsTrigger>
        </TabsList>
        <TabsContent value="list">
          {query.isPending && <PageSkeleton />}
          {query.isError && (
            <ErrorState
              message={errorMessage(query.error)}
              onRetry={() => {
                void query.refetch();
              }}
            />
          )}
          {query.data !== undefined && (
            <ListView lessons={query.data} timeZone={timeZone} today={today} />
          )}
        </TabsContent>
        <TabsContent value="week">
          <WeekView timeZone={timeZone} today={today} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
