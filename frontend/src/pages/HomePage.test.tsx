/**
 * Тест рендера страницы каркаса HomePage (T0.11; с T1.13 корнем стал роутер в App).
 * Тестируем поведение с точки зрения пользователя (docs/12 §11).
 */
import { render, screen } from "@testing-library/react";

import { HomePage } from "@/pages/HomePage";

describe("страница «Привет, Ромчик»", () => {
  it("показывает приветствие заголовком H1", () => {
    render(<HomePage />);
    const heading = screen.getByRole("heading", { level: 1 });
    expect(heading).toHaveTextContent("Привет, Ромчик");
  });

  it("показывает название приложения", () => {
    render(<HomePage />);
    expect(screen.getByText("Ромчик")).toBeInTheDocument();
  });
});
