FROM postgres:16.14-bookworm@sha256:64154d0babcb1741988719e703419af0382b19953706149f9872fbd0f438efa8

ARG POSTGRES_RUNTIME_UID=1000
ARG POSTGRES_RUNTIME_GID=1000

# bind mountしたPGDATAをホストの開発ユーザーから通常操作できるよう、
# コンテナ内postgresユーザーのUID/GIDをホストへ合わせる。
RUN groupmod --gid "${POSTGRES_RUNTIME_GID}" postgres \
    && usermod --uid "${POSTGRES_RUNTIME_UID}" \
        --gid "${POSTGRES_RUNTIME_GID}" postgres
