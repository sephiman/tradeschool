# syntax=docker/dockerfile:1.7
# SPDX-License-Identifier: AGPL-3.0-only
FROM node:26-alpine AS build
WORKDIR /workspace

COPY package.json package-lock.json .npmrc ./
RUN npm ci --no-audit --no-fund

COPY tsconfig.json tsconfig.app.json tsconfig.node.json vite.config.ts index.html ./
COPY src ./src
RUN npm run build

FROM nginx:1.29-alpine AS runtime
COPY --from=build /workspace/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
RUN echo "ok" > /usr/share/nginx/html/healthz

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- http://localhost/healthz | grep -q ok || exit 1
