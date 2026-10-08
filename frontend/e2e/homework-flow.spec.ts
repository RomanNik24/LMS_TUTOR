/**
 * Сквозной сценарий (T8.07): преподаватель выдаёт ДЗ → ученик входит и сдаёт («Сделал») →
 * преподаватель получает уведомление, оценивает → ученик получает уведомление об оценке.
 *
 * Вход — через подписанный тестовым токеном initData (как в Telegram), без подмены сервера.
 * Telegram подменён: стек запущен с TELEGRAM_API_BASE на telegram-mock-server, тест читает отправленное.
 */
import { expect, test } from "@playwright/test";
import type { APIRequestContext, Browser, Page } from "@playwright/test";

import { texts } from "../src/lib/texts";
import { E2E } from "./support/config";
import { launchUrl, signInitData } from "./support/initData";
import { sentTo } from "./support/telegramMockClient";

const TITLE = `E2E ДЗ ${String(Date.now())}`;
const MAX_SCORE = 10;
const SCORE = 9;

const owner = { id: E2E.ownerTelegramId, first_name: "Владелец" };
const student = { id: E2E.studentTelegramId, first_name: "Ученик" };

/** Сессия персонала в API-клиенте Playwright (cookie хранится в контексте запросов). */
async function staffApi(request: APIRequestContext): Promise<APIRequestContext> {
  const response = await request.post("/api/v1/auth/telegram", {
    data: { init_data: signInitData(E2E.botToken, owner) },
    headers: { "X-Requested-With": "XMLHttpRequest", Origin: E2E.baseUrl },
  });
  expect(response.status(), await response.text()).toBe(200);
  return request;
}

async function openAs(
  browser: Browser,
  user: { id: number; first_name: string },
  path: string,
  viewport: { width: number; height: number },
): Promise<Page> {
  const context = await browser.newContext({ viewport });
  const page = await context.newPage();
  await page.goto(launchUrl(E2E.baseUrl, path, signInitData(E2E.botToken, user)));
  return page;
}

test("вход → сдача ДЗ → оценка → уведомления", async ({ browser, request }) => {
  // 1. Преподаватель выдаёт задание ученику (через API: форма покрыта компонентными тестами).
  const api = await staffApi(request);
  const students = await api.get("/api/v1/admin/students", { params: { q: E2E.studentName } });
  expect(students.status()).toBe(200);
  const found = (
    (await students.json()) as { items: { user_id: number; display_name: string }[] }
  ).items.find((item) => item.display_name === E2E.studentName);
  expect(
    found,
    `в базе нет ученика «${E2E.studentName}»: выполните scripts/e2e_seed.py`,
  ).toBeDefined();
  const due = new Date(Date.now() + 3 * 24 * 3600 * 1000).toISOString();
  const created = await api.post("/api/v1/admin/homework", {
    headers: { "X-Requested-With": "XMLHttpRequest", Origin: E2E.baseUrl },
    data: {
      kind: "regular",
      title: TITLE,
      subject_code: "informatics",
      max_score: MAX_SCORE,
      due_mode: "fixed",
      due_at: due,
      student_ids: [found?.user_id],
    },
  });
  expect(created.status(), await created.text()).toBe(201);

  // 2. Ученик (экран 360 px) входит по initData, находит ДЗ и сдаёт «Сделал».
  const studentPage = await openAs(browser, student, "/app/homework", { width: 360, height: 740 });
  await expect(studentPage.getByText(TITLE)).toBeVisible();
  await studentPage.getByText(TITLE).click();
  await studentPage.getByRole("button", { name: texts.student.homework.selfReport }).click();
  await expect(studentPage.getByText(texts.student.homework.submitted)).toBeVisible();

  // 3. Преподаватель получает уведомление «сдано» (рассылка идёт фоновой задачей).
  await expect
    .poll(async () => (await sentTo(E2E.ownerTelegramId)).some((text) => text.includes(TITLE)), {
      timeout: E2E.notificationTimeoutMs,
      message: "владельцу не пришло уведомление о сданной работе",
    })
    .toBe(true);

  // 4. Преподаватель открывает работу из очереди и ставит оценку.
  const ownerPage = await openAs(browser, owner, "/admin/homework", { width: 1280, height: 800 });
  await ownerPage.getByRole("link", { name: new RegExp(TITLE) }).click();
  await ownerPage.getByLabel(texts.admin.homework.review.score).fill(String(SCORE));
  await ownerPage.getByRole("button", { name: texts.admin.homework.review.save }).click();
  await expect(ownerPage.getByText(texts.admin.homework.review.saved)).toBeVisible();

  // 5. Ученик получает уведомление «проверено» с оценкой.
  await expect
    .poll(
      async () =>
        (await sentTo(E2E.studentTelegramId)).some(
          (text) =>
            text.includes(TITLE) && text.includes(`${String(SCORE)} из ${String(MAX_SCORE)}`),
        ),
      {
        timeout: E2E.notificationTimeoutMs,
        message: "ученику не пришло уведомление об оценке",
      },
    )
    .toBe(true);

  // 6. В приложении ученика ДЗ показывается проверенным.
  await studentPage.reload();
  await expect(
    studentPage.getByText(new RegExp(`${String(SCORE)} из ${String(MAX_SCORE)}`)),
  ).toBeVisible();
});

test("ученик не попадает в Admin App, менеджерских денег на его экранах нет", async ({
  browser,
}) => {
  const page = await openAs(browser, student, "/admin/finance", { width: 360, height: 740 });
  await expect(page).not.toHaveURL(/\/admin\/finance/);
  await expect(page.locator("body")).not.toContainText(/₽|заработан/i);
});
