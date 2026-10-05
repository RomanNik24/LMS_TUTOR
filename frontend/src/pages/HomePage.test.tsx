/**
 * Тест рендера единственной страницы каркаса (T0.11).
 * Тестируем поведение с точки зрения пользователя (docs/12 §11).
 */
import { render, screen } from "@testing-library/react";

import { App } from "@/App";

describe("страница «Привет, Ромчик»", () => {
  it("показывает приветствие заголовком H1", () => {
    render(<App />);
    const heading = screen.getByRole("heading", { level: 1 });
    expect(heading).toHaveTextContent("Привет, Ромчик");
  });

  it("показывает название приложения", () => {
    render(<App />);
    expect(screen.getByText("Ромчик")).toBeInTheDocument();
  });
});
