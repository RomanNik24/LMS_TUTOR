import { CircleCheck } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { errorMessage } from "@/api/errors";
import { ErrorState } from "@/components/common/ErrorState";
import { PageHeader } from "@/components/common/PageHeader";
import { PageSkeleton } from "@/components/common/PageSkeleton";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Card } from "@/components/ui/card";
import { useSubjectName } from "@/features/reference/api";
import { formatDayKeyLong, formatDayLabel, formatTime, formatTimeRange } from "@/lib/datetime";
import { texts } from "@/lib/texts";

import { isOwnerDashboard, useTodayDashboard } from "./api";
import type { DashboardAssignmentItem, DashboardLesson, DashboardOwner } from "./api";

const t = texts.admin.dashboard;

/** «среда, 14 октября, 18:00» в поясе сотрудника. */
function whenLabel(isoUtc: string, timeZone: string): string {
  return `${formatDayLabel(isoUtc, timeZone)}, ${formatTime(isoUtc, timeZone)}`;
}

const rowLink =
  "flex flex-col gap-0.5 rounded-sm px-1 py-1.5 hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

type BlockProps = {
  title: string;
  total: number;
  shown: number;
  children: ReactNode;
  footer?: ReactNode;
};

/** Блок-карточка: заголовок со счётчиком, строки либо «Всё в порядке», «и ещё N». */
function Block({ title, total, shown, children, footer }: BlockProps) {
  return (
    <Card className="flex flex-col gap-2">
      <div className="flex items-baseline justify-between gap-2">
        <h2 className="text-base font-bold font-heading">{title}</h2>
        {total > 0 && (
          <span className="rounded-sm bg-secondary px-2 py-0.5 text-xs font-bold text-secondary-foreground font-heading">
            {total}
          </span>
        )}
      </div>
      {total === 0 ? (
        <p className="flex items-center gap-2 text-sm text-muted-foreground font-body">
          <CircleCheck className="size-5 text-success-fg" aria-hidden />
          {t.allGood}
        </p>
      ) : (
        <>
          <ul className="flex flex-col">{children}</ul>
          {total > shown && (
            <p className="text-sm text-muted-foreground font-body">{t.more(total - shown)}</p>
          )}
          {footer}
        </>
      )}
    </Card>
  );
}

function LessonRow({ lesson, timeZone }: { lesson: DashboardLesson; timeZone: string }) {
  const subjectName = useSubjectName();
  return (
    <li>
      <Link to="/admin/schedule" className={rowLink}>
        <span className="flex flex-wrap items-center gap-2 font-semibold font-body">
          {formatTimeRange(lesson.start_at, lesson.end_at, timeZone)}
          <span className="font-normal">{subjectName(lesson.subject_code)}</span>
          <StatusBadge status={`lesson.${lesson.status}`} />
          {lesson.needs_mark && (
            <span className="text-sm font-bold text-primary font-heading">{t.lessonsMark}</span>
          )}
        </span>
        <span className="text-sm text-muted-foreground font-body">
          {lesson.student_names.length === 0 ? t.noStudents : lesson.student_names.join(", ")}
        </span>
      </Link>
    </li>
  );
}

function AssignmentRow({ item, timeZone }: { item: DashboardAssignmentItem; timeZone: string }) {
  return (
    <li>
      <Link to={`/admin/assignments/${String(item.assignment_id)}`} className={rowLink}>
        <span className="font-semibold font-body">{item.student_name}</span>
        <span className="text-sm text-muted-foreground font-body">
          {item.title} · {t.dueAt(whenLabel(item.due_at, timeZone))}
        </span>
      </Link>
    </li>
  );
}

/** Ключевая цифра владельца: заработано в этом месяце — амбер-акцент экрана (docs/07 §9.2.1). */
function EarnedCard({ data }: { data: DashboardOwner }) {
  return (
    <Card className="flex flex-col gap-1 border-transparent bg-highlight text-highlight-foreground">
      <p className="text-sm font-semibold font-body">{t.earnedTitle}</p>
      <p className="text-3xl font-extrabold font-display">
        {t.earned(data.earned_month.toLocaleString("ru-RU"))}
      </p>
      <p className="text-sm font-body">{t.expected(data.expected_month.toLocaleString("ru-RU"))}</p>
    </Card>
  );
}

/** «Сегодня» (docs/07 §9.2.1): герой, финансовая карточка владельца и пять блоков дня. */
export function DashboardPage() {
  const query = useTodayDashboard();
  if (query.isPending) return <PageSkeleton cards={4} />;
  if (query.isError) {
    return (
      <ErrorState
        message={errorMessage(query.error)}
        onRetry={() => {
          void query.refetch();
        }}
      />
    );
  }
  const data = query.data;
  const timeZone = data.timezone;
  const summary =
    data.lessons.total === 0
      ? t.noLessonsSummary(data.review_queue.total)
      : t.summary(data.lessons.total, data.review_queue.total);

  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t.title} description={`${formatDayKeyLong(data.date)} · ${summary}`} />
      {isOwnerDashboard(data) && <EarnedCard data={data} />}
      <div className="grid gap-4 lg:grid-cols-2">
        <Block title={t.lessons} total={data.lessons.total} shown={data.lessons.items.length}>
          {data.lessons.items.map((lesson) => (
            <LessonRow key={lesson.id} lesson={lesson} timeZone={timeZone} />
          ))}
        </Block>
        <Block
          title={t.review}
          total={data.review_queue.total}
          shown={data.review_queue.items.length}
          footer={
            <Link
              to="/admin/homework"
              className="text-sm font-semibold text-primary underline font-body"
            >
              {t.reviewOpen}
            </Link>
          }
        >
          {data.review_queue.items.map((item) => (
            <li key={item.assignment_id}>
              <Link to={`/admin/assignments/${String(item.assignment_id)}`} className={rowLink}>
                <span className="font-semibold font-body">{item.student_name}</span>
                <span className="text-sm text-muted-foreground font-body">{item.title}</span>
              </Link>
            </li>
          ))}
        </Block>
        <Block
          title={t.unsubmitted}
          total={data.unsubmitted.total}
          shown={data.unsubmitted.items.length}
        >
          {data.unsubmitted.items.map((item) => (
            <AssignmentRow key={item.assignment_id} item={item} timeZone={timeZone} />
          ))}
        </Block>
        <Block
          title={t.unmarked}
          total={data.unmarked_lessons.total}
          shown={data.unmarked_lessons.items.length}
        >
          {data.unmarked_lessons.items.map((lesson) => (
            <li key={lesson.id}>
              <Link to="/admin/schedule" className={rowLink}>
                <span className="font-semibold font-body">
                  {whenLabel(lesson.start_at, timeZone)}
                </span>
                <span className="text-sm text-muted-foreground font-body">
                  {lesson.student_names.length === 0
                    ? t.noStudents
                    : lesson.student_names.join(", ")}
                </span>
              </Link>
            </li>
          ))}
        </Block>
        <Block title={t.deadlines} total={data.deadlines.total} shown={data.deadlines.items.length}>
          {data.deadlines.items.map((item) => (
            <AssignmentRow key={item.assignment_id} item={item} timeZone={timeZone} />
          ))}
        </Block>
      </div>
    </div>
  );
}
