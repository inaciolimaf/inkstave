# syntax=docker/dockerfile:1
#
# Inkstave backend image (spec 56). Multi-stage, Alpine, single-process. The same
# image runs the API, the ARQ worker and the (in-app) collab WebSocket — they
# differ only by the command. Build from the REPO ROOT so the LaTeX package
# config can be baked in:
#
#   docker build -f backend/Dockerfile -t inkstave-backend .

# --- Stage 1: builder — resolve the locked runtime deps into a venv ----------- #
FROM python:3.12-alpine AS builder

# Toolchain for any musl C-extension builds (argon2/cffi, asyncpg). Thrown away
# with this stage — never copied forward.
#
# NOTE (deviation from spec 56 §5.2): spec 56 lists `postgresql-dev` in this
# builder stage, but it is intentionally omitted. Inkstave talks to Postgres via
# `asyncpg`, which implements the Postgres wire protocol natively in pure
# Python/Cython and does NOT link against `libpq`/`postgresql-dev`. Adding the
# package would only bloat the build with unused C headers. Do not add it.
RUN apk add --no-cache build-base libffi-dev

# Pinned uv for reproducible, fast dependency resolution.
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app

# Deps first (cached unless the lockfile changes), then the project itself.
COPY backend/pyproject.toml backend/uv.lock backend/README.md ./
RUN uv sync --frozen --no-install-project --no-dev
COPY backend/src ./src
RUN uv sync --frozen --no-dev

# --- Stage 2: runtime — minimal Alpine + Tectonic, non-root ------------------- #
FROM python:3.12-alpine AS runtime

# Runtime OS deps only — NO compilers. Tectonic comes from Alpine community (a
# single LaTeX engine, NOT a full TeX Live); see docs/adr/0056. fontconfig + a
# base font let it lay out documents.
#
# NOTE (deviation from spec 56 §5.2): spec 56 lists `libpq` here, but it is
# intentionally omitted. `asyncpg` speaks the Postgres wire protocol natively and
# needs no `libpq` at runtime, so installing it would add an unused shared library
# to the image. Do not add it.
RUN apk add --no-cache ca-certificates fontconfig ttf-freefont tectonic \
    && addgroup -g 10001 inkstave \
    && adduser -u 10001 -G inkstave -D -H inkstave

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TECTONIC_CACHE_DIR=/var/cache/tectonic \
    COMPILE_WORKDIR_ROOT=/tmp/inkstave-compiles

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
# Application source + migrations + the bakeable LaTeX package config (compose may
# mount-override packages.toml so it can be edited without a rebuild — spec 5.7).
COPY --chown=inkstave:inkstave backend/alembic.ini ./alembic.ini
COPY --chown=inkstave:inkstave backend/migrations ./migrations
COPY --chown=inkstave:inkstave backend/src ./src
COPY --chown=inkstave:inkstave infra/tectonic/packages.toml ./infra/tectonic/packages.toml

# Writable dirs owned by the non-root user: Tectonic cache, local upload storage,
# ephemeral per-compile workdirs (the latter must stay container-local — never a
# shared named volume).
RUN mkdir -p /var/cache/tectonic /data/files /tmp/inkstave-compiles \
    && chown -R inkstave:inkstave /var/cache/tectonic /data/files /tmp/inkstave-compiles /app

USER inkstave

# Warm the Tectonic bundle/format cache at build time: compiling a trivial document
# here downloads the LaTeX format + base packages ONCE into TECTONIC_CACHE_DIR, baked
# into the image. The first runtime compile then hits this cache instead of fetching
# the whole format on demand (the slow "downloading hyph-*.tex" phase) and timing out.
RUN <<'WARM'
set -eu
cat > /tmp/warmup.tex <<'TEX'
\documentclass{article}
\begin{document}
cache warmup
\end{document}
TEX
tectonic -X compile /tmp/warmup.tex --outdir /tmp
rm -rf /tmp/warmup.tex /tmp/warmup.pdf /tmp/warmup.log /tmp/warmup.synctex.gz
WARM

EXPOSE 8000

# Liveness: the API's dependency-free /health probe (spec 02/51).
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status==200 else 1)"

# Default command: the API. The worker and (in-app) collab override the command
# in docker-compose.prod.yml.
CMD ["uvicorn", "inkstave.main:app", "--host", "0.0.0.0", "--port", "8000"]
