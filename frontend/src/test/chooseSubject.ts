import { fireEvent, screen } from "@testing-library/react";

import { texts } from "@/lib/texts";

import { SUBJECTS } from "./server";

/**
 * Выбрать предмет в форме: дождаться справочника с сервера (MSW) и выбрать пункт по коду.
 * Предмет по умолчанию не выбран — так форма не отправит его «наугад».
 */
export async function chooseSubject(code = "informatics"): Promise<void> {
  const subject = SUBJECTS.find((item) => item.code === code);
  if (subject === undefined) throw new Error(`нет предмета ${code} в справочнике тестов`);
  const option = await screen.findByRole("option", { name: subject.name });
  const select = option.closest("select");
  if (select === null) throw new Error("пункт предмета вне <select>");
  fireEvent.change(select, { target: { value: subject.code } });
  expect(screen.queryByRole("option", { name: texts.common.chooseSubject })).not.toBeNull();
}
