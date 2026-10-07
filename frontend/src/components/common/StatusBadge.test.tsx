import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { texts } from "@/lib/texts";

import { STATUS_VARIANTS, StatusBadge } from "./StatusBadge";
import type { StatusKey } from "./StatusBadge";

const KEYS = Object.keys(STATUS_VARIANTS) as StatusKey[];

describe("StatusBadge", () => {
  it("покрывает все 14 статусов docs/07 §6.6 и все тексты словаря", () => {
    expect(KEYS).toHaveLength(14);
    expect(KEYS.sort()).toEqual(Object.keys(texts.status).sort());
  });

  it.each(KEYS)("рисует статус %s с текстом и видом из таблицы", (status) => {
    render(<StatusBadge status={status} />);
    const badge = screen.getByText(texts.status[status]);
    expect(badge).toBeInTheDocument();
    expect(badge.closest("[data-variant]")).toHaveAttribute(
      "data-variant",
      STATUS_VARIANTS[status],
    );
  });
});
