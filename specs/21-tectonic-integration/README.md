# Spec 21 — Tectonic Integration (compile service)

**Type:** 🟢 feature  ·  **Phase:** Compilation  ·  **Status:** ☑ done

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. Do this:

1. **Read the requirements.** The full, authoritative requirements for this spec
   are in [`spec.md`](spec.md) next to this file. Implement *exactly* what it
   describes — no more, no less. If something is ambiguous, prefer the simplest
   option consistent with `CLAUDE.md` and stop to ask rather than invent scope.
2. **Confirm prerequisites.** This spec depends on: **13** (document content
   storage) and **14** (binary file storage abstraction). They must already be
   implemented and their tests passing.
3. **Study the Overleaf reference (for understanding only).** Read the paths in
   the "Overleaf reference" section of `spec.md` inside the cloned repo at
   `../overleaf/`. **Do not copy or translate any Overleaf code** — it is AGPLv3
   and Inkstave is MIT. Overleaf's CLSI orchestrates `latexmk` over TeX Live;
   **Inkstave uses Tectonic**, a single self-contained Rust binary. Cite Overleaf
   only for orchestration/sandboxing *concepts*, never command lines.
4. **Implement** the backend compile **service** described in `spec.md`. This
   spec delivers a *synchronous* service function; the async ARQ wrapping is
   spec 22 and output persistence is spec 23.
5. **Write the tests** listed in the spec's Test plan. **Real Tectonic compiles
   are slow** — they MUST be stubbed/mocked in unit and integration tiers. Only
   a single tiny smoke compile may run, and only in e2e (and even then it must be
   skippable in the fast path).
6. **Verify.** Run the full test suite. It must pass and the whole suite must
   stay under the 2-minute budget. Then check every Acceptance criterion and
   Definition-of-Done item.
7. **Record decisions.** Add an ADR under `docs/` for the sandbox/security model.

When all Definition-of-Done items pass, this spec is complete. Move to spec 22.

## One-line goal

The system can take a project's documents and binary files, assemble them into
an isolated working directory, run Tectonic, and return a PDF plus the captured
log — synchronously, with timeouts and resource limits enforced.

## Do NOT (scope guard)

- Do not build the HTTP API or ARQ job — that is spec 22.
- Do not persist outputs to the storage abstraction — that is spec 23.
- Do not build PDF preview UI — that is spec 24.
- Do not parse the log into structured errors — that is spec 27.
- Do not copy Overleaf source code (CLSI is AGPLv3).
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
