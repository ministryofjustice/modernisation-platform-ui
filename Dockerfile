##################################################
# Stage: uv
# From: ghcr.io/astral-sh/uv:python3.13-alpine
##################################################
FROM ghcr.io/astral-sh/uv:python3.13-alpine@sha256:b2968dc4b3d7b8e52dfbbd26d550565af4ae379148e88ddfb8723039369ab359 AS uv

##################################################
# Stage: builder
# From: docker.io/python:3.13-alpine3.22
##################################################
FROM docker.io/python:3.13-alpine3.22@sha256:41351b07080ccfaa27bf38dde20de79ee6a0ac74a58c00c6d7a7d96ac4e69716 AS builder

ARG BUILD_DEV="false"

ENV UV_COMPILE_BYTECODE=1 \
  UV_LINK_MODE="copy"

WORKDIR /app

COPY --from=uv /usr/local/bin/uv /usr/local/bin/uv

RUN --mount=type=cache,target=/root/.cache/uv \
  --mount=type=bind,source=uv.lock,target=uv.lock \
  --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
  <<EOF
if [ "${BUILD_DEV}" = "true" ]; then
  echo "BUILD_DEV is true, installing dev dependencies"
  uv sync --locked --no-install-project --no-editable
else
  uv sync --locked --no-install-project --no-editable --no-dev
fi
EOF

##################################################
# Stage: final
# From: docker.io/python:3.13-alpine3.22
##################################################
#checkov:skip=CKV_DOCKER_2: HEALTHCHECK not required - Health checks are implemented in Kubernetes as liveness and readiness probes

FROM docker.io/python:3.13-alpine3.22@sha256:41351b07080ccfaa27bf38dde20de79ee6a0ac74a58c00c6d7a7d96ac4e69716 AS final

LABEL org.opencontainers.image.vendor="Ministry of Justice" \
  org.opencontainers.image.authors="GitHub Community <modernisation-platform@digital.justice.gov.uk>" \
  org.opencontainers.image.title="GitHub Community" \
  org.opencontainers.image.description="Passionate engineers delivering great services" \
  org.opencontainers.image.url="https://github.com/ministryofjustice/modernisation-platform-ui"

ENV CONTAINER_USER="nonroot" \
  CONTAINER_UID="65532" \
  CONTAINER_GROUP="nonroot" \
  CONTAINER_GID="65532" \
  APP_HOME="/app" \
  PATH="/app/.venv/bin:${PATH}" \
  PYTHONDONTWRITEBYTECODE=1 \
  PYTHONUNBUFFERED=1 \
  PYTHONPATH="/app"


RUN <<EOF
addgroup -g ${CONTAINER_GID} ${CONTAINER_GROUP}

adduser -D -H -u ${CONTAINER_UID} -G ${CONTAINER_GROUP} ${CONTAINER_USER}

install --directory --mode=0755 --owner="${CONTAINER_USER}" --group="${CONTAINER_GROUP}" "${APP_HOME}"
EOF

WORKDIR ${APP_HOME}
COPY --from=builder --chown=${CONTAINER_UID}:${CONTAINER_GID} /app/.venv /app/.venv
COPY --chown=${CONTAINER_UID}:${CONTAINER_GID} app app
COPY --chown=nobody:nobody --chmod=0755 container/usr/local/bin/entrypoint.sh /usr/local/bin/entrypoint.sh

USER ${CONTAINER_UID}

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
