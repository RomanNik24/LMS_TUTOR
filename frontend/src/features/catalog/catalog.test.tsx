import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { beforeEach, describe, expect, it } from "vitest";

import { texts } from "@/lib/texts";
import { routes } from "@/router";
import { mockMe } from "@/test/mockMe";
import { renderRoutes } from "@/test/renderRoutes";
import { server } from "@/test/server";

import { movedIds } from "./api";
import type { CatalogItem } from "./api";

const t = texts.admin.catalog;

const card = (id: number, patch: Partial<CatalogItem> = {}): CatalogItem => ({
  id,
  title: `Услуга ${String(id)}`,
  description: `Описание ${String(id)}`,
  price_text: null,
  sort_order: id,
  is_published: false,
  ...patch,
});

function mockCatalog(items: CatalogItem[]) {
  server.use(http.get("*/api/v1/admin/catalog", () => HttpResponse.json(items)));
}

beforeEach(() => {
  mockMe("manager");
});

describe("movedIds", () => {
  it("переносит карточку на новую позицию", () => {
    const items = [card(1), card(2), card(3)];
    expect(movedIds(items, 0, 2)).toEqual([2, 3, 1]);
    expect(movedIds(items, 2, 0)).toEqual([3, 1, 2]);
    expect(movedIds(items, 1, 1)).toEqual([1, 2, 3]);
  });
});

describe("Каталог услуг", () => {
  it("пусто: подсказка добавить первую карточку", async () => {
    mockCatalog([]);
    renderRoutes(routes, ["/admin/catalog"]);
    expect(await screen.findByText(t.empty)).toBeInTheDocument();
  });

  it("список показывает статус публикации и стоимость", async () => {
    mockCatalog([card(1, { is_published: true, price_text: "от 1500 ₽" }), card(2)]);
    renderRoutes(routes, ["/admin/catalog"]);
    expect(await screen.findByText("Услуга 1")).toBeInTheDocument();
    expect(screen.getByText(t.published)).toBeInTheDocument();
    expect(screen.getByText(t.hidden)).toBeInTheDocument();
    expect(screen.getByText("от 1500 ₽")).toBeInTheDocument();
    expect(screen.getByText(t.noPrice)).toBeInTheDocument();
  });

  it("«Ниже» отправляет новый порядок на сервер", async () => {
    mockCatalog([card(1), card(2), card(3)]);
    let sent: unknown = null;
    server.use(
      http.put("*/api/v1/admin/catalog/order", async ({ request }) => {
        sent = await request.json();
        return HttpResponse.json([card(2), card(1), card(3)]);
      }),
    );
    renderRoutes(routes, ["/admin/catalog"]);
    fireEvent.click(await screen.findByRole("button", { name: `${t.moveDown}: Услуга 1` }));
    await waitFor(() => {
      expect(sent).toEqual({ ids: [2, 1, 3] });
    });
    const titles = await screen.findAllByRole("heading", { level: 2 });
    expect(titles.map((node) => node.textContent)).toEqual(["Услуга 2", "Услуга 1", "Услуга 3"]);
  });

  it("крайние карточки не двигаются за край", async () => {
    mockCatalog([card(1), card(2)]);
    renderRoutes(routes, ["/admin/catalog"]);
    expect(await screen.findByRole("button", { name: `${t.moveUp}: Услуга 1` })).toBeDisabled();
    expect(screen.getByRole("button", { name: `${t.moveDown}: Услуга 2` })).toBeDisabled();
  });

  it("публикация меняет только is_published", async () => {
    mockCatalog([card(1)]);
    let body: unknown = null;
    server.use(
      http.patch("*/api/v1/admin/catalog/1", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(card(1, { is_published: true }));
      }),
    );
    renderRoutes(routes, ["/admin/catalog"]);
    fireEvent.click(await screen.findByRole("button", { name: `${t.publish}: Услуга 1` }));
    await waitFor(() => {
      expect(body).toEqual({ is_published: true });
    });
  });

  it("создание: валидация и отправка; пустая стоимость уходит как null", async () => {
    mockCatalog([]);
    let body: unknown = null;
    server.use(
      http.post("*/api/v1/admin/catalog", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(card(5), { status: 201 });
      }),
    );
    renderRoutes(routes, ["/admin/catalog"]);
    fireEvent.click(await screen.findByRole("button", { name: t.newItem }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: t.form.submitCreate }));
    expect(await within(dialog).findByText(t.form.titleRequired)).toBeInTheDocument();
    expect(within(dialog).getByText(t.form.descriptionRequired)).toBeInTheDocument();
    expect(body).toBeNull();

    fireEvent.change(within(dialog).getByLabelText(t.form.title), { target: { value: " ЕГЭ " } });
    fireEvent.change(within(dialog).getByLabelText(t.form.description), {
      target: { value: "Подготовка" },
    });
    fireEvent.click(within(dialog).getByLabelText(t.form.publish));
    fireEvent.click(within(dialog).getByRole("button", { name: t.form.submitCreate }));
    await waitFor(() => {
      expect(body).toEqual({
        title: "ЕГЭ",
        description: "Подготовка",
        price_text: null,
        is_published: true,
      });
    });
  });

  it("удаление — после подтверждения", async () => {
    mockCatalog([card(1)]);
    let deleted = false;
    server.use(
      http.delete("*/api/v1/admin/catalog/1", () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderRoutes(routes, ["/admin/catalog"]);
    fireEvent.click(await screen.findByRole("button", { name: `${t.delete}: Услуга 1` }));
    expect(deleted).toBe(false);
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: t.deleteConfirm }));
    await waitFor(() => {
      expect(deleted).toBe(true);
    });
  });

  it("ошибка загрузки: «Повторить»", async () => {
    server.use(
      http.get("*/api/v1/admin/catalog", () =>
        HttpResponse.json(
          { error: { code: "internal_error", message: "x", details: {} } },
          { status: 500 },
        ),
      ),
    );
    renderRoutes(routes, ["/admin/catalog"]);
    const alert = await screen.findByRole("alert");
    expect(within(alert).getByRole("button")).toBeInTheDocument();
  });
});
