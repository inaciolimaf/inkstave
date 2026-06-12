# Spec 51 — Observability

**Type:** 🟢 feature  ·  **Phase:** Hardening, packaging & docs  ·  **Status:** ☐ not started

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. Do this:

1. **Read the requirements.** The full, authoritative requirements for this spec
   are in [`spec.md`](spec.md) next to this file. Implement *exactly* what it
   describes — no more, no less. If something is ambiguous, prefer the simplest
   option consistent with `CLAUDE.md` and stop to ask rather than invent scope.
2. **Confirm prerequisites.** This spec depends on: **02** (FastAPI app,
   settings, logging skeleton, error handling, health endpoints). It also
   touches every prior subsystem (WS in 28–34, ARQ jobs in 22/44, the agent in
   41–49), so those must already be implemented and their tests passing.
3. **Study the Overleaf reference (for understanding only).** Read the paths in
   the "Overleaf reference" section of `spec.md` inside the cloned repo at
   `../overleaf/`. **Do not copy or translate any Overleaf code** — it is AGPLv3
   and Inkstave is MIT. Learn the approach, then write your own implementation.
4. **Implement** the backend changes described in `spec.md`.
5. **Write the tests** listed in the spec's Test plan (unit / integration).
6. **Verify.** Run the full test suite. It must pass and the whole suite must
   stay under the 2-minute budget. Then check every Acceptance criterion and
   Definition-of-Done item.
7. **Record decisions.** If you made an architectural decision (e.g. metrics
   library choice, OTel on/off by default), add a short note under `docs/`.

When all Definition-of-Done items pass, this spec is complete. Move to spec 52.

## One-line goal

Every request, WebSocket session and background job carries a propagated
request/trace ID through structured JSON logs, and the service exposes a
Prometheus-style `/metrics` endpoint plus deepened health/readiness probes.

## Do NOT (scope guard)

- Do not implement features that belong to later specs (rate limiting and secure
  headers are spec 52; CI budget gates are spec 53).
- Do not copy Overleaf source code (read `libraries/logger`, `libraries/metrics`
  only to learn the approach).
- Do not introduce technologies outside the approved stack (`CLAUDE.md`). Use a
  Prometheus client and an OTel SDK only as additive, well-scoped libraries.
- Do not add heavyweight tracing exporters that run in the fast test tiers.
