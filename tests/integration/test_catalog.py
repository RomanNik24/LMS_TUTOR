"""Каталог услуг (T8.01): CRUD персонала, порядок, публикация, витрина для вошедших."""

# ruff: noqa: F401, F811 - фикстуры подключаются импортом из test_schedule_api

import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.models import CatalogItem
from src.services.catalog import CatalogService
from tests.integration.test_schedule_api import (
    AuthedClient,
    anya,
    anya_client,
    app,
    boris,
    manager,
    owner,
    owner_user,
    redis_clean,
)

ADMIN = "/api/v1/admin/catalog"


async def create(client: AuthedClient, title: str, **extra: object) -> dict[str, object]:
    response = await client.post(
        ADMIN, json={"title": title, "description": f"Описание {title}", **extra}
    )
    assert response.status_code == 201, response.text
    body: dict[str, object] = response.json()
    return body


async def test_create_appends_to_end_and_is_unpublished_by_default(owner: AuthedClient) -> None:
    first = await create(owner, "Подготовка к ЕГЭ", price_text="от 1500 ₽")
    second = await create(owner, "Подготовка к ОГЭ")

    assert (first["sort_order"], second["sort_order"]) == (0, 1)
    assert first["is_published"] is False
    assert first["price_text"] == "от 1500 ₽"
    assert second["price_text"] is None


async def test_student_sees_only_published_in_order(
    owner: AuthedClient, anya_client: AuthedClient
) -> None:
    a = await create(owner, "А")
    b = await create(owner, "Б", is_published=True)
    c = await create(owner, "В", is_published=True)
    hidden = await owner.get(ADMIN)
    assert [item["title"] for item in hidden.json()] == ["А", "Б", "В"]

    await owner.patch(f"{ADMIN}/{c['id']}", json={"sort_order": 0})
    await owner.patch(f"{ADMIN}/{b['id']}", json={"sort_order": 1})
    await owner.patch(f"{ADMIN}/{a['id']}", json={"is_published": True, "sort_order": 2})

    shown = await anya_client.get("/api/v1/catalog")
    assert shown.status_code == 200
    assert [item["title"] for item in shown.json()] == ["В", "Б", "А"]
    # публичная схема не содержит служебных полей
    assert set(shown.json()[0]) == {"id", "title", "description", "price_text"}

    await owner.patch(f"{ADMIN}/{a['id']}", json={"is_published": False})
    again = await anya_client.get("/api/v1/catalog")
    assert [item["title"] for item in again.json()] == ["В", "Б"]


async def test_patch_clears_price_and_validates(owner: AuthedClient) -> None:
    item = await create(owner, "Услуга", price_text="500 ₽")

    cleared = await owner.patch(f"{ADMIN}/{item['id']}", json={"price_text": None})
    assert cleared.status_code == 200
    assert cleared.json()["price_text"] is None
    assert (await owner.patch(f"{ADMIN}/{item['id']}", json={})).status_code == 422
    assert (await owner.patch(f"{ADMIN}/{item['id']}", json={"title": "   "})).status_code == 422
    assert (await owner.patch(f"{ADMIN}/{item['id']}", json={"title": None})).status_code == 422
    assert (await owner.patch(f"{ADMIN}/{item['id']}", json={"extra": 1})).status_code == 422
    missing = await owner.patch(f"{ADMIN}/9999", json={"title": "x"})
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "catalog_item_not_found"


async def test_reorder_requires_all_ids_once(owner: AuthedClient) -> None:
    ids = [(await create(owner, name))["id"] for name in ("А", "Б", "В")]

    ok = await owner.put(f"{ADMIN}/order", json={"ids": [ids[2], ids[0], ids[1]]})
    assert ok.status_code == 200
    assert [item["title"] for item in ok.json()] == ["В", "А", "Б"]
    assert [item["sort_order"] for item in ok.json()] == [0, 1, 2]
    for bad in ([ids[0]], [ids[0], ids[0], ids[1]], [*ids, 9999]):
        response = await owner.put(f"{ADMIN}/order", json={"ids": bad})
        assert response.status_code == 422, bad


async def test_delete(owner: AuthedClient) -> None:
    item = await create(owner, "Лишняя")

    assert (await owner.delete(f"{ADMIN}/{item['id']}")).status_code == 204
    assert (await owner.delete(f"{ADMIN}/{item['id']}")).status_code == 404
    assert (await owner.get(ADMIN)).json() == []


async def test_manager_can_manage_and_student_cannot(
    manager: AuthedClient, anya_client: AuthedClient
) -> None:
    item = await create(manager, "От менеджера", is_published=True)
    assert item["is_published"] is True

    for call in (
        anya_client.get(ADMIN),
        anya_client.post(ADMIN, json={"title": "x", "description": "y"}),
        anya_client.patch(f"{ADMIN}/{item['id']}", json={"title": "x"}),
        anya_client.put(f"{ADMIN}/order", json={"ids": [item["id"]]}),
        anya_client.delete(f"{ADMIN}/{item['id']}"),
    ):
        assert (await call).status_code == 403


async def test_catalog_requires_login(app: FastAPI) -> None:
    import httpx  # noqa: PLC0415

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as anonymous:
        assert (await anonymous.get("/api/v1/catalog")).status_code == 401


async def test_service_list_published_needs_no_actor(db_session: AsyncSession) -> None:
    db_session.add_all(
        [
            CatalogItem(title="Видна", description="d", is_published=True, sort_order=1),
            CatalogItem(title="Скрыта", description="d", is_published=False, sort_order=0),
        ]
    )
    await db_session.commit()

    titles = [item.title for item in await CatalogService(db_session).list_published()]

    assert titles == ["Видна"]
