# Spec 52 — Security Hardening

**Type:** 🟢 feature  ·  **Phase:** Hardening, packaging & docs  ·  **Status:** ☐ not started

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. Do this:

1. **Read the requirements.** The full, authoritative requirements for this spec
   are in [`spec.md`](spec.md) next to this file. Implement *exactly* what it
   describes — no more, no less. If something is ambiguous, prefer the simplest
   option consistent with `CLAUDE.md` and stop to ask rather than invent scope.
2. **Confirm prerequisites.** This spec depends on: **08** (auth guards,
   sessions, current-user dependency — what the auth rate limiter and the
   middleware chain attach to), **34** (access control across REST/WS/compile —
   authz is assumed correct and is reinforced, not re-implemented, here), and
   **49** (agent rate limits & cost controls — extended into the shared limiter).
   All must be implemented and green. Spec **51**'s middleware chain and request
   context should exist so security middleware slots in cleanly.
3. **Study the Overleaf reference (for understanding only).** Read the paths in
   the "Overleaf reference" section of `spec.md` inside the cloned repo at
   `../overleaf/`. **Do not copy or translate any Overleaf code** — it is AGPLv3
   and Inkstave is MIT. Learn the approach, then write your own implementation.
4. **Implement** the backend changes and the security checklist in `spec.md`.
5. **Write the tests** listed in the spec's Test plan (unit / integration).
6. **Verify.** Run the full test suite under the 2-minute budget, then check
   every Acceptance criterion and Definition-of-Done item.
7. **Record decisions.** Add a short security ADR + the checklist under `docs/`.

When all Definition-of-Done items pass, this spec is complete. Move to spec 53.

## One-line goal

Inkstave is hardened cross-cutting: Redis-backed rate limits on sensitive
endpoints, strict Pydantic validation, a CORS allow-list, secure HTTP headers, a
reviewed/sandboxed compile path with the trusted-users caveat reaffirmed, upload
sanitization, and a dependency-audit gate — captured in a security checklist.

## Do NOT (scope guard)

- Do not implement features that belong to later specs; do not re-architect
  authz (spec 34 owns it — only reinforce and add tests for gaps).
- Do not build a multi-tenant compile sandbox beyond the CE trusted-users model;
  reaffirm the caveat and apply the resource isolation spec 21 established.
- Do not copy Overleaf source code (read its security middleware for approach
  only).
- Do not introduce technologies outside the approved stack (`CLAUDE.md`). Use
  Redis (already present) for rate limiting; do not add a new datastore.
