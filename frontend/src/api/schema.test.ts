// Проверка сгенерированных типов API (T1.12): файл schema.d.ts подключается,
// а нужные пути и ответы в нём есть. Несовпадение типов ловит `pnpm typecheck`.
import type { components, paths } from "./schema";

type MeResponse = components["schemas"]["MeResponse"];
type MeOk = paths["/api/v1/me"]["get"]["responses"]["200"]["content"]["application/json"];
type LoginBody =
  paths["/api/v1/auth/telegram"]["post"]["requestBody"]["content"]["application/json"];

describe("api schema types", () => {
  it("MeResponse содержит только публичные поля", () => {
    const me: MeOk = { id: 1, role: "student", display_name: "Аня", timezone: "Europe/Moscow" };
    const same: MeResponse = me;
    expect(Object.keys(same).sort()).toEqual(["display_name", "id", "role", "timezone"]);
  });

  it("тело входа через Telegram — init_data", () => {
    const body: LoginBody = { init_data: "query_id=AAH" };
    expect(body.init_data).toBeTruthy();
  });
});
