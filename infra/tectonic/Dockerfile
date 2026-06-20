# syntax=docker/dockerfile:1
#
# inkstave-tectonic — the OFFLINE LaTeX compile image (spec 105).
#
# This image is what the SandboxedTectonicRunner launches, once per compile, in an
# ephemeral gVisor (runsc) container with NO network. It therefore bakes the pinned
# LaTeX package set into the Tectonic cache at BUILD time so runtime compiles work
# with `--network none --only-cached`.
#
# Build from the REPO ROOT so the package set is in context:
#
#   docker build --network=host -f infra/tectonic/Dockerfile -t inkstave-tectonic .
#
# `--network=host` is required for the cache-warmup step (it must reach Tectonic's
# IPv6-advertising CDN, which the default build bridge cannot route — same reason as
# backend/Dockerfile). The RUNTIME container never has network.
#
# Keep the warmup package list in sync with infra/tectonic/packages.toml `[packages]
# prewarm`: Tectonic resolves transitive dependencies automatically, so list only the
# top-level packages a document `\usepackage{...}`s.

# --- Stage 1: warm the Tectonic cache for the pinned package set -------------- #
FROM alpine:3.20 AS warm

# Tectonic from Alpine community (a single LaTeX engine, not a full TeX Live) plus
# fontconfig + a base font so it can lay documents out. Same engine as the backend.
RUN apk add --no-cache ca-certificates fontconfig ttf-freefont tectonic

ENV TECTONIC_CACHE_DIR=/var/cache/tectonic

# Compile a document that \usepackage's the whole pinned prewarm set so every package
# (and the LaTeX format + hyphenation files) lands in the cache, baked into the image.
RUN <<'WARM'
set -eu
mkdir -p /var/cache/tectonic
cat > /tmp/prewarm.tex <<'TEX'
\documentclass{article}
\usepackage{amsmath}
\usepackage{amsfonts}
\usepackage{amssymb}
\usepackage{geometry}
\usepackage{graphicx}
\usepackage{hyperref}
\usepackage[english]{babel}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{xcolor}
\usepackage{booktabs}
\usepackage{caption}
\usepackage{enumitem}
\usepackage{listings}
\begin{document}
prewarm $E=mc^2$
\end{document}
TEX
tectonic -X compile /tmp/prewarm.tex --outdir /tmp
rm -rf /tmp/prewarm.*
WARM

# --- Stage 2: runtime — Tectonic + the warmed cache, non-root, no network ----- #
FROM alpine:3.20 AS runtime

RUN apk add --no-cache ca-certificates fontconfig ttf-freefont tectonic

ENV TECTONIC_CACHE_DIR=/var/cache/tectonic

# Carry only the warmed cache forward (no build tooling).
COPY --from=warm /var/cache/tectonic /var/cache/tectonic

# The SandboxedTectonicRunner runs the container as user 65534 (nobody) against a
# read-only root, so the cache must be world-readable. The compile reads /work (the
# read-only project mount) and writes only to /out and the /tmp tmpfs.
RUN chmod -R a+rX /var/cache/tectonic

USER 65534:65534
WORKDIR /work

# NO ENTRYPOINT on purpose: the SandboxedTectonicRunner passes the FULL argv
# (`tectonic -X compile … --outdir /out --only-cached`) as the container command, so
# `tectonic` is resolved from PATH as the executable. Setting an entrypoint would
# double it (`tectonic tectonic …`). The runner also adds `--user 65534`, so the
# image USER is only a defence-in-depth default.
