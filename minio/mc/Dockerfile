# Локальная сборка MinIO Client (mc) из официального исходника строгой версии
# RELEASE.2025-08-13T08-35-41Z (задача T0.07).
#
# Готовые community-образы minio/mc больше не публикуются (source-only), поэтому
# клиент собирается локально из официального репозитория https://github.com/minio/mc,
# строго по тегу релиза (никаких `latest` и сторонних зеркал).
#
# Используется в docker-compose.yml (`minio-init`, build: ./minio/mc).
# Итоговый образ: lms-mc:RELEASE.2025-08-13T08-35-41Z

ARG MC_VERSION=RELEASE.2025-08-13T08-35-41Z

# ---------- Слой сборки: go + make + git ----------
FROM golang:1.24-bookworm AS builder

ARG MC_VERSION

ENV CGO_ENABLED=0 \
    GOFLAGS=-buildvcs=false

WORKDIR /build

# Тонкий checkout строгой версии: mc не требует подмодулей, GOFLAGS не мешает.
RUN git clone --depth 1 --branch "${MC_VERSION}" \
        https://github.com/minio/mc.git src && \
    cd src && \
    echo "Собираем mc из тега: $(git describe --tags)"

# go build -o /build/mc . — официальная цель (Makefile: `go build -o minio`).
RUN cd src && \
    go build -trimpath -ldflags="-w -s" -o /build/mc . && \
    /build/mc --version

# ---------- Слой запуска: минимальный образ без лишних утилит ----------
# ca-certificates нужен mc для TLS-соединений к MinIO по HTTPS.
FROM debian:bookworm-slim AS runtime

RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Непривилегированный пользователь (uid/gid 10002 — не пересекается с
# minio-user 10001 в образе minio-сервера).
RUN groupadd --system --gid 10002 mc-user && \
    useradd --system --uid 10002 --gid mc-user --home-dir /home/mc \
            --shell /usr/sbin/nologin mc-user

COPY --from=builder /build/mc /usr/bin/mc

USER 10002:10002

WORKDIR /home/mc

# ENTRYPOINT намеренно НЕ задан: сервис minio-init в docker-compose.yml
# запускает скрипт через `sh -c "..."`, поэтому Entrypoint должен
# оставаться нейтральным, иначе Compose подставит его перед `sh`.
CMD ["/usr/bin/mc", "--version"]
