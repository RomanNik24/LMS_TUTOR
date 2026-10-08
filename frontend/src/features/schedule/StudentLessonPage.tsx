import { ArrowLeft, ExternalLink } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { errorMessage } from "@/api/errors";
import { ErrorState } from "@/components/common/ErrorState";
import { PageSkeleton } from "@/components/common/PageSkeleton";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useMe } from "@/features/auth/api";
import { DEFAULT_TIMEZONE } from "@/features/students/studentForm";
import { formatDayLabel, formatTime, formatTimeRange } from "@/lib/datetime";
import { formatDate } from "@/lib/datetime";
import { texts } from "@/lib/texts";
import { useSubjectName } from "@/features/reference/api";

import { useStudentLesson } from "./studentApi";

const t = texts.student.schedule.card;

/** Карточка урока ученика (docs/07 §9.1.3): время, статус, ссылки; без цен и заметок. */
export function StudentLessonPage() {
  const subjectLabel = useSubjectName();
  const { lessonId } = useParams();
  const { data: me } = useMe();
  const timeZone = me?.timezone ?? DEFAULT_TIMEZONE;
  const query = useStudentLesson(Number(lessonId));

  const back = (
    <Button asChild variant="ghost" size="compact" className="self-start">
      <Link to="/app/schedule">
        <ArrowLeft className="size-4" aria-hidden />
        {t.back}
      </Link>
    </Button>
  );

  if (query.isPending) return <PageSkeleton cards={2} />;
  if (query.isError) {
    return (
      <div className="flex flex-col gap-4">
        {back}
        <ErrorState
          message={errorMessage(query.error)}
          onRetry={() => {
            void query.refetch();
          }}
        />
      </div>
    );
  }
  const lesson = query.data;
  return (
    <div className="flex flex-col gap-4">
      {back}
      <Card className="flex flex-col gap-3">
        <span className="self-start rounded-sm bg-secondary px-2 py-1 text-xs font-bold text-secondary-foreground font-heading">
          {subjectLabel(lesson.subject_code)}
        </span>
        <h1 className="text-xl font-extrabold font-display">
          {formatTimeRange(lesson.start_at, lesson.end_at, timeZone)}
        </h1>
        <p className="text-sm font-body">{formatDayLabel(lesson.start_at, timeZone)}</p>
        <div>
          <StatusBadge status={`lesson.${lesson.status}`} />
        </div>
        {lesson.topic !== null && (
          <p className="text-sm font-body">
            <span className="text-muted-foreground">{t.topic}: </span>
            {lesson.topic}
          </p>
        )}
        {lesson.participants_count > 1 && (
          <p className="text-sm text-muted-foreground font-body">
            {t.group(lesson.participants_count)}
          </p>
        )}
      </Card>
      <div className="flex flex-col gap-2">
        {lesson.video_url !== null && (
          <Button asChild variant="highlight">
            <a href={lesson.video_url} target="_blank" rel="noopener noreferrer">
              <ExternalLink className="size-4" aria-hidden />
              {t.video}
            </a>
          </Button>
        )}
        {lesson.board_url !== null && (
          <Button asChild variant="outline">
            <a href={lesson.board_url} target="_blank" rel="noopener noreferrer">
              <ExternalLink className="size-4" aria-hidden />
              {t.board}
            </a>
          </Button>
        )}
        {lesson.video_url === null && lesson.board_url === null && (
          <p className="text-sm text-muted-foreground font-body">{t.noLinks}</p>
        )}
      </div>
      {lesson.homework.length > 0 && (
        <section aria-labelledby="lesson-homework" className="flex flex-col gap-2">
          <h2 id="lesson-homework" className="text-base font-bold font-heading">
            {t.homework}
          </h2>
          {lesson.homework.map((item) => (
            <Card key={item.assignment_id} className="flex flex-col gap-2">
              <Link
                to={`/app/homework/${String(item.assignment_id)}`}
                className="text-base font-semibold text-primary font-body"
              >
                {item.title}
              </Link>
              <p className="text-sm text-muted-foreground font-body">
                {t.homeworkDue(
                  `${formatDate(item.due_at, timeZone)}, ${formatTime(item.due_at, timeZone)}`,
                )}
              </p>
              <div>
                <StatusBadge
                  status={item.is_overdue ? "homework.overdue" : `homework.${item.status}`}
                />
              </div>
            </Card>
          ))}
        </section>
      )}
    </div>
  );
}
