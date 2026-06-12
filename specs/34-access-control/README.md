# Spec 34 — Access control (centralized authorization)

**Type:** 🟢 feature  ·  **Phase:** Real-time collaboration  ·  **Status:** ☑ done

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. Do this:

1. **Read the requirements.** The full, authoritative requirements for this spec
   are in [`spec.md`](spec.md) next to this file. Implement *exactly* what it
   describes — no more, no less. If something is ambiguous, prefer the simplest
   option consistent with `CLAUDE.md` and stop to ask rather than invent scope.
2. **Confirm prerequisites.** This spec depends on: **33** (membership/role data
   model: `project_memberships`, roles owner/editor/viewer), **29** (the collab
   WebSocket and its room join) and **22** (the compile API + ARQ job). It also
   assumes specs 11–14 (project/file/doc/binary endpoints) and 31/32 (frontend
   binding + presence) exist.
3. **Study the Overleaf reference (for understanding only).** Read the paths in
   the "Overleaf reference" section of `spec.md` inside the cloned repo at
   `../overleaf/`. **Do not copy or translate any Overleaf code** — it is AGPLv3
   and Inkstave is MIT. Learn the *centralized authorization* approach (a single
   manager + middleware, a privilege-levels concept), then implement your own.
4. **Implement** a single authorization service + a role→capability matrix, and
   **retrofit** consistent guards onto the existing REST project/doc/file/compile
   endpoints and the spec-29 WebSocket join (read-only Yjs for viewers).
5. **Write the tests** listed in the spec's Test plan (pytest unit/integration
   across REST + WS + compile; a tiny Vitest check for the read-only editor).
6. **Verify.** Run the full test suite (< 2 min). Check every Acceptance
   criterion and Definition-of-Done item.
7. **Record decisions.** If you made an architectural decision (e.g. where the
   guard lives, how viewer read-only is enforced on the CRDT), add an ADR in `docs/`.

When all Definition-of-Done items pass, this spec is complete. Move to spec 35.

## One-line goal

Every project surface — REST (project/doc/file), the collaboration WebSocket, and
compile — consistently enforces project membership and role, so non-members are
denied, viewers are read-only everywhere (including the live CRDT), and editors/
owners get the access their role allows.

## Do NOT (scope guard)

- Do not change the sharing data model or invite flow — consume spec 33's
  `project_memberships`/roles as given.
- Do not change the CRDT wire protocol (spec 28) or the WS framing (spec 29)
  beyond adding an authorization gate at join and a server-side write-rejection
  for viewers.
- Do not build an admin panel or site-admin/superuser roles — out of scope.
- Do not implement public/link sharing or anonymous access.
- Do not copy Overleaf source code.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
