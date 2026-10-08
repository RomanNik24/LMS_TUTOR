import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Card } from "@/components/ui/card";
import { formatDayKey } from "@/lib/datetime";
import { texts } from "@/lib/texts";

import type { StudentReport } from "./api";

const t = texts.student.reports;

/** Размер до первого измерения контейнера: график рисуется сразу, а не пустым (и в тестах). */
const INITIAL_SIZE = { width: 320, height: 200 } as const;
const CHART_HEIGHT = 200;
const PERCENT_TICKS = [0, 25, 50, 75, 100];

type Point = { label: string; percent: number; hint: string };

type ChartCardProps = {
  title: string;
  points: Point[];
  axisX: string;
  axisY: string;
  seriesName: string;
  /** Текст при отсутствии точек. */
  emptyText: string;
  /** Подпись-итог рядом с заголовком (например, «Последний результат: 78%»). */
  badge?: string;
  summary: string[];
};

/**
 * Линейный график с подписями осей, пустым состоянием и текстовой сводкой для доступности
 * (docs/07 §6.15, §10): смысл графика понятен и без картинки.
 */
function ChartCard({
  title,
  points,
  axisX,
  axisY,
  seriesName,
  emptyText,
  badge,
  summary,
}: ChartCardProps) {
  return (
    <Card className="flex flex-col gap-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-base font-bold font-heading">{title}</h2>
        {badge !== undefined && (
          <span className="rounded-sm bg-secondary px-2 py-1 text-xs font-bold text-secondary-foreground font-heading">
            {badge}
          </span>
        )}
      </div>
      {points.length === 0 ? (
        <p className="text-sm text-muted-foreground font-body">{emptyText}</p>
      ) : (
        <>
          <div role="img" aria-label={title} style={{ height: CHART_HEIGHT }}>
            <ResponsiveContainer width="100%" height="100%" initialDimension={INITIAL_SIZE}>
              <LineChart data={points} margin={{ top: 8, right: 12, bottom: 20, left: 0 }}>
                <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
                <XAxis
                  dataKey="label"
                  stroke="var(--muted-foreground)"
                  tick={{ fontSize: 12 }}
                  label={{
                    value: axisX,
                    position: "insideBottom",
                    offset: -12,
                    fontSize: 12,
                    fill: "var(--muted-foreground)",
                  }}
                />
                <YAxis
                  domain={[0, 100]}
                  ticks={PERCENT_TICKS}
                  width={36}
                  stroke="var(--muted-foreground)"
                  tick={{ fontSize: 12 }}
                  label={{
                    value: axisY,
                    angle: -90,
                    position: "insideLeft",
                    offset: 12,
                    fontSize: 12,
                    fill: "var(--muted-foreground)",
                  }}
                />
                <Tooltip
                  formatter={(value) => [`${String(value)}%`, seriesName]}
                  contentStyle={{
                    background: "var(--card)",
                    border: "1px solid var(--border)",
                    borderRadius: 8,
                  }}
                />
                <Line
                  type="monotone"
                  dataKey="percent"
                  name={seriesName}
                  stroke="var(--primary)"
                  strokeWidth={2}
                  dot={{ r: 4, fill: "var(--primary)" }}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <ul className="flex flex-col gap-1 text-sm text-muted-foreground font-body">
            {summary.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </>
      )}
    </Card>
  );
}

type ReportChartsProps = {
  report: StudentReport;
};

/**
 * Три блока отчёта (docs/07 §9.1.6): средний процент ДЗ по неделям, пробные экзамены,
 * «Сдано в срок». Данные приходят готовыми из API; здесь только отрисовка и подписи.
 */
export function ReportCharts({ report }: ReportChartsProps) {
  const weekly = report.homework_weekly.map((point) => ({
    label: formatDayKey(point.week_start),
    percent: point.average_percent,
    hint: t.homework.weekPoint(
      formatDayKey(point.week_start),
      point.average_percent,
      point.graded_count,
    ),
  }));
  const mock = report.mock_exams.map((point) => {
    const label = formatDayKey(point.exam_date);
    const result =
      point.scale_applicable && point.converted_value !== null
        ? point.result_kind === "grade_2_5"
          ? texts.exams.gradeLabel(point.converted_value)
          : texts.exams.testLabel(point.converted_value)
        : texts.exams.notApplicable;
    return {
      label,
      percent: point.percent,
      hint: t.mock.point(label, point.exam_type_name, `${result} (${String(point.percent)}%)`),
    };
  });
  const { on_time: onTime } = report;

  return (
    <div className="flex flex-col gap-4">
      <ChartCard
        title={t.homework.title}
        points={weekly}
        axisX={t.homework.axisWeek}
        axisY={t.homework.axisPercent}
        seriesName={t.homework.series}
        emptyText={t.homework.none}
        badge={
          report.homework_last_percent === null
            ? undefined
            : t.homework.last(report.homework_last_percent)
        }
        summary={weekly.map((point) => point.hint)}
      />
      <ChartCard
        title={t.mock.title}
        points={mock}
        axisX={t.mock.axisDate}
        axisY={t.mock.axisPercent}
        seriesName={t.mock.series}
        emptyText={t.mock.none}
        summary={mock.map((point) => point.hint)}
      />
      <Card className="flex flex-col gap-1">
        <h2 className="text-base font-bold font-heading">{t.onTime.title}</h2>
        {onTime.percent === null ? (
          <p className="text-sm text-muted-foreground font-body">{t.onTime.none}</p>
        ) : (
          <>
            <p className="text-3xl font-extrabold font-display">{t.onTime.value(onTime.percent)}</p>
            <p className="text-sm text-muted-foreground font-body">
              {t.onTime.detail(onTime.on_time_count, onTime.total_count)}
            </p>
          </>
        )}
      </Card>
    </div>
  );
}
