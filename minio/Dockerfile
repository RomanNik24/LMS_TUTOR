# syntax=docker/dockerfile:1
# Локальная сборка MinIO Community Edition из исходников (исправление T0.07).
#
# Причина: готовые community Docker-образы minio/minio больше не публикуются;
# согласно официальному репозиторию https://github.com/minio/minio,
# Community Edition распространяется как source-only, и образ рекомендуется
# собирать через `docker build` (ориентир — официальные Makefile targets
# `docker` / `getrelease`). Данный Dockerfile делает то же самое и пригоден
# для docker-compose.yml (сервис `minio`, build: ./minio).
#
# Версия строго зафиксирована: RELEASE.2025-10-15T17-29-55Z
# (последний релиз, для которого опубликованы официальные инструкции по
# самостоятельной сборке). Никаких `latest`.

ARG MINIO_VERSION=RELEASE.2025-10-15T17-29-55Z

# ---------- Этап builder: сборка бинарника minio из исходников ----------
FROM golang:1.24-bookworm AS builder

ARG MINIO_VERSION

ENV CGO_ENABLED=0 \
    GOFLAGS=-buildvcs=false

WORKDIR /build

# Клонируем официальный репозиторий без полного дерева истории и делаем
# checkout строго нужного релизного тега.
RUN git clone --depth 1 --branch "${MINIO_VERSION}" \
        https://github.com/minio/minio.git src && \
    cd src && \
    echo "Собирается тег: $(git describe --tags)"

# Статическая сборка минимально необходимого бинарника сервера MinIO
# (эквивалент официального `make release` в части бинарника `minio`).
RUN cd src && \
    go build -trimpath -ldflags="-w -s" -o /build/minio . && \
    /build/minio --version

# ---------- Этап runtime: минимальный образ только с необходимым ----------
FROM debian:bookworm-slim AS runtime

# Минимальные пакеты для запуска и проверки здоровья сервера:
# ca-certificates — TLS, curl — healthcheck GET /minio/health/live.
RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates curl && \
    rm -rf /var/lib/apt/lists/*

# Непривилегированный пользователь с фиксированными uid/gid (совместимо с
# официальной раскладкой образа MinIO: /usr/bin/minio, /data).
RUN groupadd --system --gid 10001 minio-user && \
    useradd --system --uid 10001 --gid minio-user --home-dir /data \
            --shell /usr/sbin/nologin minio-user && \
    mkdir -p /data && chown -R 10001:10001 /data

COPY --from=builder /build/minio /usr/bin/minio

# Данные — внутри контейнера, принадлежат непривилегированному пользователю
# (volume minio_data монтируется в /data).
VOLUME /data

USER 10001:10001

EXPOSE 9000 9001

WORKDIR /data

ENTRYPOINT ["/usr/bin/minio"]
CMD ["server", "/data"]
