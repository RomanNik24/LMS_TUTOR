import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Card } from "@/components/ui/card";
import { formatDayKey } from "@/lib/datetime";
import { texts } from "@/lib/texts";

import type { EarningsRow } from "./api";

const t = texts.admin.finance;

/** Размер до первого измерения контейнера: график рисуется сразу, а не пустым (и в тестах). */
const INITIAL_SIZE = { width: 320, height: 220 } as const;
const CHART_HEIGHT = 220;

type EarningsChartProps = {
  /** Строки отчёта в разрезе «по неделям» (ключ — понедельник `yyyy-MM-dd`). */
  weeks: EarningsRow[];
};

/**
 * Столбчатый график «Заработано по неделям» с подписями осей и текстовой сводкой для доступности
 * (docs/07 §6.15, §10).
 */
export function EarningsChart({ weeks }: EarningsChartProps) {
  const points = weeks
    .filter((row) => row.earned > 0)
    .map((row) => ({ label: formatDayKey(row.key), key: row.key, earned: row.earned }));

  return (
    <Card className="flex flex-col gap-3">
      <h2 className="text-base font-bold font-heading">{t.chartTitle}</h2>
      {points.length === 0 ? (
        <p className="text-sm text-muted-foreground font-body">{t.chartNone}</p>
      ) : (
        <>
          <div role="img" aria-label={t.chartTitle} style={{ height: CHART_HEIGHT }}>
            <ResponsiveContainer width="100%" height="100%" initialDimension={INITIAL_SIZE}>
              <BarChart data={points} margin={{ top: 8, right: 12, bottom: 20, left: 0 }}>
                <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
                <XAxis
                  dataKey="label"
                  stroke="var(--muted-foreground)"
                  tick={{ fontSize: 12 }}
                  label={{
                    value: t.chartAxisX,
                    position: "insideBottom",
                    offset: -12,
                    fontSize: 12,
                    fill: "var(--muted-foreground)",
                  }}
                />
                <YAxis
                  width={56}
                  stroke="var(--muted-foreground)"
                  tick={{ fontSize: 12 }}
                  label={{
                    value: t.chartAxisY,
                    angle: -90,
                    position: "insideLeft",
                    offset: 4,
                    fontSize: 12,
                    fill: "var(--muted-foreground)",
                  }}
                />
                <Tooltip
                  formatter={(value) => [t.money(Number(value)), t.chartSeries]}
                  contentStyle={{
                    background: "var(--card)",
                    border: "1px solid var(--border)",
                    borderRadius: 8,
                  }}
                />
                <Bar
                  dataKey="earned"
                  name={t.chartSeries}
                  fill="var(--primary)"
                  radius={[4, 4, 0, 0]}
                  isAnimationActive={false}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <ul className="flex flex-col gap-1 text-sm text-muted-foreground font-body">
            {points.map((point) => (
              <li key={point.key}>{t.chartPoint(point.label, point.earned)}</li>
            ))}
          </ul>
        </>
      )}
    </Card>
  );
}
