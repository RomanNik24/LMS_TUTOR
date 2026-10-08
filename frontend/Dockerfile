# syntax=docker/dockerfile:1
# Образ фронтенда: сборка SPA (pnpm build) → Nginx со статикой и прокси на backend
# (docs/10 §3, задача T1.17). Контекст сборки — КОРЕНЬ репозитория (нужен каталог nginx/):
#   docker build -f frontend/Dockerfile .
# В Compose это делает сервис `nginx` (профиль `full`).

# ---------- Этап build: pnpm install --frozen-lockfile → pnpm build ----------
# Node 22 — та же линия, что в CI (.github/workflows/ci.yml) и frontend/.nvmrc.
FROM node:22-slim AS build

# pnpm берётся из packageManager в package.json (corepack), версия не плавает.
RUN corepack enable

WORKDIR /app

# Сначала манифесты и lock: слой с зависимостями пересобирается только при их изменении.
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

COPY frontend/ ./

# Публичные значения VITE_* вшиваются в сборку (секретов во фронтенде нет, docs/02 §7).
ARG VITE_BOT_USERNAME=""
ENV VITE_BOT_USERNAME=${VITE_BOT_USERNAME}
# Публичный DSN Sentry (необязательно): без него Sentry не загружается.
ARG VITE_SENTRY_DSN=""
ENV VITE_SENTRY_DSN=${VITE_SENTRY_DSN}

# pnpm build = tsc --noEmit && vite build → /app/dist
RUN pnpm build

# ---------- Этап runtime: Nginx со статикой ----------
FROM nginx:1.28-alpine AS runtime

# Исправления безопасности ОС поверх базового образа (nginx, openssl, pcre2, zlib, curl...):
# в базовом теге они появляются с задержкой (docs/ops/SECURITY_CHECK.md, T8.10).
RUN apk upgrade --no-cache

# Стандартный default.conf образа заменяется нашим; snippets подключаются через include.
RUN rm -f /etc/nginx/conf.d/default.conf
COPY nginx/conf.d/default.conf /etc/nginx/conf.d/default.conf
COPY nginx/snippets/ /etc/nginx/snippets/
# Шаблоны с переменными окружения: штатный entrypoint образа nginx при старте подставляет
# значения (envsubst) и пишет готовые файлы в /etc/nginx/<тот же путь без .template>.
# Подставляется только S3_PUBLIC_ENDPOINT (адрес подписанных ссылок хранилища для CSP img-src);
# по умолчанию пусто — картинки только со своего домена.
COPY nginx/templates/ /etc/nginx/templates/
ENV NGINX_ENVSUBST_OUTPUT_DIR=/etc/nginx \
    NGINX_ENVSUBST_FILTER=^(S3_PUBLIC_ENDPOINT|CSP_CONNECT_EXTRA)\$ \
    S3_PUBLIC_ENDPOINT="" \
    CSP_CONNECT_EXTRA=""
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

# /health проксируется на backend: «healthy» значит, что работают и Nginx, и app.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["wget", "-q", "-O", "/dev/null", "http://127.0.0.1/health"]
