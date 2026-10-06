import { useNavigate, useParams } from "react-router-dom";

import { errorMessage } from "@/api/errors";
import { ErrorState } from "@/components/common/ErrorState";
import { texts } from "@/lib/texts";

import { useLinkLogin } from "../api";

/**
 * Вход по одноразовой ссылке /login/:token (docs/09 §2.3). Открытие страницы (GET)
 * НИЧЕГО не меняет: токен гасится только POST-запросом по нажатию «Войти» — так
 * предпросмотр ссылки мессенджером или антивирусом её не «сжигает».
 */
export function LinkLoginPage() {
  const { token } = useParams();
  const navigate = useNavigate();
  const login = useLinkLogin();

  const submit = () => {
    if (token === undefined) {
      return;
    }
    login.mutate(token, {
      onSuccess: () => {
        void navigate("/", { replace: true });
      },
    });
  };

  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-6 bg-[image:var(--hero-gradient)] px-4 text-center">
      <h1 className="text-2xl font-extrabold uppercase tracking-tight text-hero-foreground font-display">
        {texts.login.title}
      </h1>
      <p className="text-base text-hero-foreground font-body">{texts.login.linkHint}</p>
      {login.isError && (
        <div className="rounded-lg bg-background p-4">
          <ErrorState message={errorMessage(login.error)} />
        </div>
      )}
      <button
        type="button"
        onClick={submit}
        disabled={login.isPending || token === undefined}
        className="min-h-11 rounded-md bg-background px-6 text-primary font-body disabled:opacity-60"
      >
        {login.isPending ? texts.login.signingIn : texts.login.linkButton}
      </button>
    </main>
  );
}
