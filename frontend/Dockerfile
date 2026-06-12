# syntax=docker/dockerfile:1
#
# Inkstave frontend image (spec 56): build the Vite SPA, then serve it from nginx
# which also reverse-proxies /api and /ws to the backend. Build from the REPO ROOT
# so the nginx config under infra/ is in context:
#
#   docker build -f frontend/Dockerfile -t inkstave-frontend .
#
# The bundle talks to the API/WS on the SAME ORIGIN (empty base) so nginx routes
# everything; override VITE_API_BASE_URL only for a split-origin deployment.

# --- Stage 1: builder — Vite production build --------------------------------- #
FROM node:20-alpine AS builder
# Pin pnpm to the version that produced the committed lockfile (pnpm@9.15.4,
# lockfileVersion 9.0). corepack otherwise downloads the latest pnpm, which now
# requires Node >= 22.13 and crashes on this Node 20 base. The `packageManager`
# field lives in frontend/package.json (not the /app workspace root corepack sees
# here), so we activate the version explicitly.
RUN corepack enable && corepack prepare pnpm@9.15.4 --activate
WORKDIR /app

# Deps first for layer caching. This is a pnpm WORKSPACE: the lockfile and the
# workspace manifest live at the REPO ROOT, not under frontend/. Copy the root
# lockfile + workspace manifest, then the frontend package manifest, so
# `--frozen-lockfile` resolves the committed root pnpm-lock.yaml.
COPY pnpm-lock.yaml pnpm-workspace.yaml ./
COPY frontend/package.json ./frontend/
RUN pnpm install --frozen-lockfile

COPY frontend/ ./frontend/
WORKDIR /app/frontend
# Same-origin API + WS so the nginx proxy handles routing (empty base).
ARG VITE_API_BASE_URL=""
ARG VITE_COLLAB_WS_URL=""
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL \
    VITE_COLLAB_WS_URL=$VITE_COLLAB_WS_URL
RUN pnpm build

# --- Stage 2: runtime — nginx serving dist + reverse proxy -------------------- #
FROM nginx:1.27-alpine AS runtime
# Replace the stock config with Inkstave's (gzip, server_tokens off, proxy rules).
RUN rm -f /etc/nginx/conf.d/default.conf
COPY infra/nginx/nginx.conf /etc/nginx/nginx.conf
COPY infra/nginx/default.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/frontend/dist /usr/share/nginx/html

EXPOSE 80
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=5 \
    CMD wget -qO- http://127.0.0.1/healthz >/dev/null 2>&1 || exit 1
# Base image's CMD already runs nginx in the foreground; workers drop to the
# unprivileged "nginx" user (the standard nginx master/worker model).
