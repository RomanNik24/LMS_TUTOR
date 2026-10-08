import { Download } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { errorMessage } from "@/api/errors";
import { ErrorState } from "@/components/common/ErrorState";
import { PageHeader } from "@/components/common/PageHeader";
import { PageSkeleton } from "@/components/common/PageSkeleton";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useMe } from "@/features/auth/api";
import { DEFAULT_TIMEZONE } from "@/features/students/studentForm";
import { shiftDayKey, todayKey } from "@/lib/datetime";
import { texts } from "@/lib/texts";

import { downloadEarningsCsv, periodRange, useCancellations, useEarnings } from "./api";
import type { EarningsGroupBy, PeriodMode } from "./api";
import { EarningsChart } from "./EarningsChart";

const t = texts.admin.finance;

const MODES: PeriodMode[] = ["week", "month", "custom"];
const SLICES: Extract<EarningsGroupBy, "student" | "subject">[] = ["student", "subject"];

type StatCardProps = { title: string; value: string; detail?: string; accent?: boolean };

/** Карточка-показатель; одна из карточек экрана — амбер-акцент (docs/07 §9.2.11). */
function StatCard({ title, value, detail, accent = false }: StatCardProps) {
  return (
    <Card
      className={
        accent
          ? "flex flex-col gap-1 border-transparent bg-highlight text-highlight-foreground"
          : "flex flex-col gap-1"
      }
    >
      <p className="text-sm font-semibold font-body">{title}</p>
      <p className="text-2xl font-extrabold font-display">{value}</p>
      {detail !== undefined && <p className="text-sm font-body">{detail}</p>}
    </Card>
  );
}

function isSlice(value: string): value is "student" | "subject" {
  return value === "student" || value === "subject";
}

function isMode(value: string): value is PeriodMode {
  return MODES.some((mode) => mode === value);
}

/** «Финансы и статистика» (docs/07 §9.2.11): только владелец. Менеджеру маршрут недоступен. */
export function FinancePage() {
  const { data: me } = useMe();
  const timeZone = me?.timezone ?? DEFAULT_TIMEZONE;
  const [mode, setMode] = useState<PeriodMode>("month");
  const [slice, setSlice] = useState<"student" | "subject">("student");
  const [custom, setCustom] = useState(() => {
    const today = todayKey(timeZone);
    return { from: shiftDayKey(today, -29), to: today };
  });
  const [exporting, setExporting] = useState(false);
  const range = periodRange(mode, custom, timeZone);
  const breakdown = useEarnings(range, slice);
  const weekly = useEarnings(range, "week");
  const cancellations = useCancellations(range);

  const onExport = () => {
    if (range === null) return;
    setExporting(true);
    downloadEarningsCsv(range, t.exportFile)
      .catch((error: unknown) => {
        toast.error(`${t.exportFailed}. ${errorMessage(error)}`);
      })
      .finally(() => {
        setExporting(false);
      });
  };

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title={t.title}
        actions={
          <Button
            size="compact"
            variant="outline"
            loading={exporting}
            disabled={range === null}
            onClick={onExport}
          >
            <Download className="size-5" aria-hidden />
            {t.export}
          </Button>
        }
      />
      <Tabs
        value={mode}
        onValueChange={(next) => {
          if (isMode(next)) setMode(next);
        }}
      >
        <TabsList aria-label={t.periodLabel}>
          {MODES.map((item) => (
            <TabsTrigger key={item} value={item}>
              {t.periods[item]}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>
      {mode === "custom" && (
        <div className="flex flex-col gap-2 sm:flex-row">
          <label className="flex flex-1 flex-col gap-1 text-sm font-medium font-body">
            {t.from}
            <Input
              type="date"
              value={custom.from}
              invalid={range === null}
              onChange={(event) => {
                setCustom({ ...custom, from: event.target.value });
              }}
            />
          </label>
          <label className="flex flex-1 flex-col gap-1 text-sm font-medium font-body">
            {t.to}
            <Input
              type="date"
              value={custom.to}
              invalid={range === null}
              onChange={(event) => {
                setCustom({ ...custom, to: event.target.value });
              }}
            />
          </label>
        </div>
      )}
      {range === null && (
        <p role="alert" className="text-sm text-destructive font-body">
          {t.invalidPeriod}
        </p>
      )}
      {range !== null && (breakdown.isPending || weekly.isPending) && <PageSkeleton cards={3} />}
      {(breakdown.isError || weekly.isError || cancellations.isError) && (
        <ErrorState
          message={errorMessage(breakdown.error ?? weekly.error ?? cancellations.error)}
          onRetry={() => {
            void breakdown.refetch();
            void weekly.refetch();
            void cancellations.refetch();
          }}
        />
      )}
      {breakdown.data !== undefined && (
        <>
          <div className="grid gap-4 sm:grid-cols-3">
            <StatCard accent title={t.earned} value={t.money(breakdown.data.earned_total)} />
            <StatCard title={t.expected} value={t.money(breakdown.data.expected_total)} />
            <StatCard
              title={t.cancellations}
              value={String(cancellations.data?.cancelled_lessons ?? 0)}
              detail={
                cancellations.data === undefined
                  ? undefined
                  : t.cancellationsDetail(
                      cancellations.data.cancelled_lessons,
                      cancellations.data.cancelled_participations,
                    )
              }
            />
          </div>
          {weekly.data !== undefined && <EarningsChart weeks={weekly.data.rows} />}
          <Tabs
            value={slice}
            onValueChange={(next) => {
              if (isSlice(next)) setSlice(next);
            }}
          >
            <TabsList aria-label={t.sliceLabel}>
              {SLICES.map((item) => (
                <TabsTrigger key={item} value={item}>
                  {t.slices[item]}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
          <Card className="overflow-x-auto p-0">
            <table className="w-full min-w-[480px] text-left text-sm font-body">
              <thead className="border-b border-border text-muted-foreground">
                <tr>
                  <th scope="col" className="px-4 py-2 font-semibold">
                    {slice === "student" ? t.colStudent : t.colSubject}
                  </th>
                  <th scope="col" className="px-4 py-2 text-right font-semibold">
                    {t.colEarned}
                  </th>
                  <th scope="col" className="px-4 py-2 text-right font-semibold">
                    {t.colExpected}
                  </th>
                  <th scope="col" className="px-4 py-2 text-right font-semibold">
                    {t.colLessons}
                  </th>
                </tr>
              </thead>
              <tbody>
                {breakdown.data.rows.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="px-4 py-4 text-muted-foreground">
                      {t.tableEmpty}
                    </td>
                  </tr>
                ) : (
                  breakdown.data.rows.map((row) => (
                    <tr key={row.key} className="border-b border-border last:border-0">
                      <th scope="row" className="px-4 py-2 font-semibold">
                        {row.label}
                      </th>
                      <td className="px-4 py-2 text-right">{t.money(row.earned)}</td>
                      <td className="px-4 py-2 text-right">{t.money(row.expected)}</td>
                      <td className="px-4 py-2 text-right">
                        {row.earned_lessons + row.planned_lessons}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </Card>
        </>
      )}
    </div>
  );
}
