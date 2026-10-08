import type { ExamType } from "@/features/reference/api";
import { texts } from "@/lib/texts";

import type { ScoreConversion } from "./api";

const t = texts.exams;

type ConversionLineProps = {
  conversion: ScoreConversion;
  examType: ExamType;
  primaryScore: number;
};

/**
 * Результат конвертации словами: «17 баллов = оценка 5», «27 баллов = тестовый 78» или
 * «Шкала не применима». Само значение считает сервер; здесь только подпись (docs/06 B2).
 */
export function ConversionLine({ conversion, examType, primaryScore }: ConversionLineProps) {
  const { converted_value: value, scale_applicable: applicable, warning } = conversion;
  const text =
    applicable && value !== null
      ? examType.result_kind === "grade_2_5"
        ? t.gradeOf(primaryScore, value)
        : t.testOf(primaryScore, value)
      : t.notApplicable;
  return (
    <div className="flex flex-col gap-1" aria-live="polite">
      <p className="text-base font-bold font-heading">{text}</p>
      {warning === "geometry_missing" && (
        <p className="text-sm text-warning-fg font-body">{t.geometryMissing}</p>
      )}
    </div>
  );
}
