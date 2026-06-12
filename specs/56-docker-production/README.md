# Spec 56 — Docker Production Packaging

**Type:** 🟢 feature  ·  **Phase:** Phase 7 — Hardening, packaging & docs  ·  **Status:** ☑ done

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. Do this:

1. **Read the requirements.** The full, authoritative requirements for this spec
   are in [`spec.md`](spec.md) next to this file. Implement *exactly* what it
   describes — no more, no less. If something is ambiguous, prefer the simplest
   option consistent with `CLAUDE.md` and stop to ask rather than invent scope.
2. **Confirm prerequisites.** This spec depends on: **01** (monorepo layout, base
   `docker-compose.yml`, `.env.example`) and **all service specs** built so far —
   the FastAPI backend (02), the ARQ worker (22, 39, 44), the collab/WebSocket
   process (28, 29), the Tectonic compiler (21), and the built frontend (09+).
   They must already be implemented and their tests passing.
3. **Study the Overleaf reference (for understanding only).** Read the paths in
   the "Overleaf reference" section of `spec.md` inside the cloned repo at
   `../overleaf/`. **Do not copy or translate any Overleaf code** — it is AGPLv3
   and Inkstave is MIT. Note Overleaf ships a *single* phusion/runit "monolith"
   container; Inkstave ships **separate, lightweight, single-process Alpine
   containers**. Learn the proxy and packaging *approach* only.
4. **Implement** the production Dockerfiles (multi-stage, Alpine), the production
   `docker-compose.prod.yml`, the nginx reverse-proxy config, healthchecks, the
   volume strategy, and wire the editable `infra/tectonic/packages.toml`.
5. **Write the tests** listed in the spec's Test plan: build-and-smoke checks and
   nginx-routing config assertions. Keep image builds out of the 2-minute unit
   budget (they run in a separate CI job — see spec 57).
6. **Verify.** Run the verification commands in `spec.md`. Then check every
   Acceptance criterion and Definition-of-Done item.
7. **Record decisions.** Add a short ADR under `docs/` noting the
   one-container-per-process choice, the Tectonic-on-musl decision, and the
   image-size targets.

When all Definition-of-Done items pass, this spec is complete. Move to spec 57.

## One-line goal

Inkstave can be built and run as a set of small, multi-stage Alpine Docker images
(backend+Tectonic, frontend+nginx, ARQ worker, collab/WS) orchestrated by a
production `docker-compose` behind an nginx reverse proxy, with healthchecks,
sane volumes, and an editable LaTeX package config.

## Do NOT (scope guard)

- Do not implement the CI/CD pipeline, migration-on-deploy, or the admin
  bootstrap — that is spec **57**.
- Do not write user/admin documentation — that is spec **58**.
- Do not bundle a full TeX Live; keep the default package set minimal (see §5.7).
- Do not collapse services into one phusion/runit container (that is Overleaf's
  approach, not Inkstave's).
- Do not copy Overleaf source code or config files.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
