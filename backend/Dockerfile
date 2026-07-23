# syntax=docker/dockerfile:1.7
# SPDX-License-Identifier: AGPL-3.0-only
# Build context is the repository ROOT (so the image can bake in ./content).
# See docker-compose.yml: services.backend.build.{context: ., dockerfile: backend/Dockerfile}.
FROM python:3.14-slim AS build
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

# Install dependencies first (cached until the lockfile changes), then the project itself.
COPY backend/pyproject.toml backend/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev
COPY backend/README.md ./
COPY backend/src ./src
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

FROM python:3.14-slim AS runtime
# curl for the container healthcheck.
RUN apt-get update \
  && apt-get install -y --no-install-recommends curl \
  && rm -rf /var/lib/apt/lists/*
RUN groupadd -g 10001 app && useradd -u 10001 -g app -m -d /app -s /usr/sbin/nologin app
WORKDIR /app

COPY --from=build --chown=app:app /app /app
# Course content is baked into the image; CONTENT_DIR points here.
COPY --chown=app:app content /app/content

ENV PATH="/app/.venv/bin:$PATH" \
    CONTENT_DIR=/app/content \
    PYTHONUNBUFFERED=1
USER app:app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD curl -fsS http://localhost:8000/api/health | grep -q '"status":"ok"' || exit 1

CMD ["uvicorn", "tradeschool.main:app", "--host", "0.0.0.0", "--port", "8000"]
