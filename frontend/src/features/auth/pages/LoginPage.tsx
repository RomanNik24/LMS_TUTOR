import { useEffect, useRef } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { errorMessage } from "@/api/errors";
import { ErrorState } from "@/components/common/ErrorState";
import { FullScreenLoader } from "@/components/common/FullScreenLoader";
import { getInitData, isTelegramMiniApp } from "@/lib/telegram";
import { texts } from "@/lib/texts";
import { externalLinkProps } from "@/lib/externalLink";

import { useTelegramLogin } from "../api";
import { returnPathFrom } from "../redirect";

const BOT_USERNAME = import.meta.env.VITE_BOT_USERNAME;

/**
 * Экран /login (docs/07 §9.3, docs/12 §5.1). Внутри Telegram — автовход по initData;
 * в обычном браузере — подсказка «Войди через Telegram-бота» с кнопкой на бота.
 */
export function LoginPage() {
  const navigate = useNavigate();
  const target = returnPathFrom(useLocation().state) ?? "/";
  const login = useTelegramLogin();
  const inMiniApp = isTelegramMiniApp();
  // StrictMode в dev запускает эффекты дважды: автовход должен отправиться один раз
  const started = useRef(false);

  const { mutate } = login;
  useEffect(() => {
    const initData = getInitData();
    if (!inMiniApp || initData === null || started.current) {
      return;
    }
    started.current = true;
    mutate(initData, {
      onSuccess: () => {
        void navigate(target, { replace: true });
      },
    });
  }, [inMiniApp, mutate, navigate, target]);

  if (inMiniApp && !login.isError) {
    return <FullScreenLoader />;
  }

  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-6 bg-[image:var(--hero-gradient)] px-4">
      <h1 className="text-2xl font-extrabold uppercase tracking-tight text-hero-foreground font-display">
        {texts.login.title}
      </h1>
      {login.isError ? (
        <div className="rounded-lg bg-background p-4">
          <ErrorState
            message={errorMessage(login.error)}
            onRetry={() => {
              const initData = getInitData();
              if (initData !== null) {
                login.mutate(initData, {
                  onSuccess: () => {
                    void navigate(target, { replace: true });
                  },
                });
              }
            }}
          />
        </div>
      ) : (
        <>
          <p className="text-base text-hero-foreground font-body">{texts.login.openViaBot}</p>
          {BOT_USERNAME !== undefined && BOT_USERNAME !== "" && (
            <a
              {...externalLinkProps(`https://t.me/${BOT_USERNAME}`)}
              className="inline-flex min-h-11 items-center rounded-md bg-background px-5 text-primary font-body"
            >
              {texts.login.openBot}
            </a>
          )}
        </>
      )}
    </main>
  );
}
