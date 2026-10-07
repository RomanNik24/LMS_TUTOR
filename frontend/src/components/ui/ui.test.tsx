import { fireEvent, render, screen } from "@testing-library/react";
import { Inbox } from "lucide-react";
import { describe, expect, it, vi } from "vitest";

import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { texts } from "@/lib/texts";

import { Button } from "./button";

describe("Button", () => {
  it("в состоянии loading недоступна для нажатия", () => {
    const onClick = vi.fn();
    render(
      <Button loading onClick={onClick}>
        Сохранить
      </Button>,
    );
    const button = screen.getByRole("button");
    expect(button).toBeDisabled();
    fireEvent.click(button);
    expect(onClick).not.toHaveBeenCalled();
  });
});

describe("ErrorState", () => {
  it("показывает текст и вызывает «Повторить»", () => {
    const onRetry = vi.fn();
    render(<ErrorState message="Не получилось" onRetry={onRetry} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Не получилось");
    fireEvent.click(screen.getByRole("button", { name: texts.login.retry }));
    expect(onRetry).toHaveBeenCalledOnce();
  });
});

describe("EmptyState", () => {
  it("показывает заголовок", () => {
    render(<EmptyState icon={Inbox} title="Пока пусто" />);
    expect(screen.getByText("Пока пусто")).toBeInTheDocument();
  });
});

describe("ConfirmDialog", () => {
  it("подтверждает действие и закрывается по «Назад»", () => {
    const onConfirm = vi.fn();
    const onOpenChange = vi.fn();
    render(
      <ConfirmDialog
        open
        onOpenChange={onOpenChange}
        title="Отменить урок?"
        confirmLabel="Отменить урок"
        onConfirm={onConfirm}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Отменить урок" }));
    expect(onConfirm).toHaveBeenCalledOnce();
    fireEvent.click(screen.getByRole("button", { name: texts.common.back }));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});
