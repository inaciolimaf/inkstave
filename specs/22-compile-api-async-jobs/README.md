# Spec 22 — Compile API & Async ARQ Jobs

**Type:** 🟢 feature  ·  **Phase:** Compilation  ·  **Status:** ☑ done

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. Do this:

1. **Read the requirements.** The full, authoritative requirements for this spec
   are in [`spec.md`](spec.md) next to this file. Implement *exactly* what it
   describes — no more, no less. If something is ambiguous, prefer the simplest
   option consistent with `CLAUDE.md` and stop to ask rather than invent scope.
2. **Confirm prerequisites.** This spec depends on: **21** (the synchronous
   compile service) and the **ARQ job infrastructure** established by specs
   **02** (backend foundation) and **04** (testing foundation). They must
   already be implemented and their tests passing.
3. **Study the Overleaf reference (for understanding only).** Read the paths in
   the "Overleaf reference" section of `spec.md` inside the cloned repo at
   `../overleaf/`. **Do not copy or translate any Overleaf code** — it is AGPLv3
   and Inkstave is MIT. Overleaf compiles *synchronously over HTTP* via CLSI;
   Inkstave compiles **asynchronously via ARQ jobs**. Use Overleaf only for the
   request/lock/concurrency *concepts*.
4. **Implement** the compile HTTP API, the ARQ job that runs the spec-21
   service, status polling, and live status streaming (SSE or WS).
5. **Write the tests** listed in the spec's Test plan. **The spec-21 compile
   service MUST be stubbed/mocked** in every test tier — no real Tectonic runs
   here.
6. **Verify.** Run the full test suite. It must pass and stay under the 2-minute
   budget. Then check every Acceptance criterion and Definition-of-Done item.
7. **Record decisions.** Add an ADR if you introduce a new pattern (e.g. the
   debounce/concurrency model).

When all Definition-of-Done items pass, this spec is complete. Move to spec 23.

## One-line goal

A user can trigger a compile via the API, which enqueues an ARQ job that runs the
spec-21 service in the background, and can watch the compile move through
queued → running → success/failure by polling or subscribing to a live stream.

## Do NOT (scope guard)

- Do not run Tectonic synchronously inside the request — it must be an ARQ job.
- Do not persist or serve the PDF/log bytes — that is spec 23 (this spec records
  *status/metadata* only and hands artifacts to spec 23 via the result shape).
- Do not build the preview UI — that is spec 24.
- Do not copy Overleaf source code (CLSI is AGPLv3).
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
