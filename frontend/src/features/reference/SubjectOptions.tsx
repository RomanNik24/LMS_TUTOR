import { texts } from "@/lib/texts";

import { useSubjects } from "./api";

/**
 * Варианты для `<select>` предмета: пустой пункт «Выберите предмет» и предметы из справочника.
 * Пустой пункт нужен, пока справочник грузится: форма не отправит предмет «наугад».
 */
export function SubjectOptions() {
  const { data } = useSubjects();
  return (
    <>
      <option value="">{texts.common.chooseSubject}</option>
      {(data ?? []).map((subject) => (
        <option key={subject.code} value={subject.code}>
          {subject.name}
        </option>
      ))}
    </>
  );
}
