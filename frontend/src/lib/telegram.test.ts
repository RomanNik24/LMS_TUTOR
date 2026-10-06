import { beforeEach, describe, expect, it, vi } from "vitest";

// SDK подменяем: проверяем только то, как lib/telegram.ts им пользуется
const sdk = vi.hoisted(() => ({
  supported: true,
  mounted: false,
  mount: vi.fn(),
  show: vi.fn(),
  hide: vi.fn(),
  off: vi.fn(),
  onClick: vi.fn(),
}));

vi.mock("@telegram-apps/sdk-react", () => ({
  isTMA: () => false,
  init: vi.fn(),
  miniApp: { isMounted: () => false, isDark: () => false },
  backButton: {
    isSupported: () => sdk.supported,
    isMounted: () => sdk.mounted,
    mount: sdk.mount,
    show: sdk.show,
    hide: sdk.hide,
    onClick: sdk.onClick,
  },
}));

import { initTelegram, showBackButton } from "./telegram";

describe("lib/telegram", () => {
  beforeEach(() => {
    sdk.supported = true;
    sdk.mounted = false;
    sdk.onClick.mockReset().mockReturnValue(sdk.off);
    sdk.mount.mockReset();
    sdk.show.mockReset();
    sdk.hide.mockReset();
    sdk.off.mockReset();
  });

  it("showBackButton монтирует, показывает кнопку и подписывает обработчик", () => {
    const onBack = vi.fn();
    showBackButton(onBack);
    expect(sdk.mount).toHaveBeenCalledOnce();
    expect(sdk.show).toHaveBeenCalledOnce();
    expect(sdk.onClick).toHaveBeenCalledWith(onBack);
  });

  it("функция отписки прячет кнопку и снимает обработчик", () => {
    const dispose = showBackButton(vi.fn());
    dispose();
    expect(sdk.off).toHaveBeenCalledOnce();
    expect(sdk.hide).toHaveBeenCalledOnce();
  });

  it("вне Telegram (кнопка не поддерживается) ничего не делает и не падает", () => {
    sdk.supported = false;
    const dispose = showBackButton(vi.fn());
    dispose();
    expect(sdk.show).not.toHaveBeenCalled();
    expect(sdk.onClick).not.toHaveBeenCalled();
  });

  it("ошибка SDK не ломает приложение", () => {
    sdk.show.mockImplementation(() => {
      throw new Error("sdk failed");
    });
    expect(() => showBackButton(vi.fn())()).not.toThrow();
  });

  it("initTelegram вне Mini App возвращает false", () => {
    expect(initTelegram()).toBe(false);
  });
});
