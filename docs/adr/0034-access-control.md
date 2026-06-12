# ADR 0034 — Centralized access control: capability matrix, leak policy, WS enforcement

- **Status:** Accepted
- **Date:** 2026-06-10
- **Context spec:** 34 — Access control (centralized authorization)

## Context

Before this spec each project router enforced access ad-hoc via
`get_owned_project` (owner-only). Spec 33 introduced `project_memberships` with
roles. Spec 34 centralizes authorization into one service + matrix and retrofits a
single guard across REST, the collab WebSocket, and compile, so roles are enforced
uniformly.

## Decisions

### 1. One matrix, one service, one dependency

`authorization/capabilities.py` holds the **authoritative role→capability matrix**
(the single source of truth). Role resolution is performed by `role_for` plus the
access-control dependency's `_resolve` helper, which read a user's role from
memberships and authorize capabilities against the matrix. (Originally this spec
introduced an `AuthorizationService` class for that role resolution; it was
**removed in spec 35** — the collaboration refactor, see
[`docs/refactors/35-collaboration.md`](../refactors/35-collaboration.md) F-2 —
and replaced by `role_for` + `_resolve`. This sentence is updated to reflect that
current reality while preserving the original decision's intent.)
`require_capability(cap)` is a FastAPI
dependency applied to every project-scoped route; it returns the loaded `Project`
(matching the old `owned_project` shape, so handlers barely changed). The previous
per-router `owned_project` helpers were removed.

**Matrix (viewer-compile enabled):** owner = all; editor = reads + `DOC_WRITE`,
`FILE_WRITE`, `COLLAB_WRITE`, `COMPILE` (no `PROJECT_WRITE`/`DELETE`/`SHARE`);
viewer = `PROJECT_READ`, `DOC_READ`, `FILE_READ`, `COLLAB_READ`, `COMPILE`;
non-member = none.

### 2. Single-query guard (no extra round trips)

The dependency loads the project row **and** the caller's active role in one
outer-join query, cached on `request.state`. This keeps the per-request query
count identical to the old owner-only check (the `test_refactor_15` query-count
budgets still pass).

### 3. 404-vs-403 leak policy

- Unauthenticated → **401** (spec-08 dependency, before authz).
- Authenticated **non-member** of a project (or a missing/soft-deleted project) →
  **404** uniformly on every project sub-resource — existence is never disclosed
  (consistent with ADR 0007). Path-param UUID validation still yields **422**.
- Authenticated **member with an insufficient role** → **403** `insufficient_role`.

Sharing endpoints (spec 33) keep their own `require_owner`/`require_member` checks
(which already produce 404 non-member / 403 non-owner consistent with the matrix's
`PROJECT_SHARE`); they were left intact rather than double-gated.

### 4. Viewer compile policy

**Viewers MAY compile** by default (`COMPILE_ALLOWED_FOR_VIEWERS=true`) — a
read-only collaborator still needs the rendered PDF. Set the flag false to make
compile editor+. Changing compile *settings* remains `PROJECT_WRITE` (owner).

### 5. WebSocket enforcement

At room join, the spec-29 handshake now calls the matrix: a **non-member** is
closed with **4403** (an existing but soft-deleted project / unknown document is
**4404**) and never added to the room or sent any sync/awareness. A **viewer**
joins with `Connection.can_write = False`; the dispatch loop **drops** their Yjs
`SyncUpdate`/`SyncStep2` frames — never applied to the pycrdt doc, persisted, or
broadcast — while they still receive others' updates and awareness (the server is
the real boundary, not just the client `readOnly`). Editor/owner are `can_write`
and behave exactly as before (no spec-29/31 regression).

### 6. Mid-session revocation — best-effort

Membership changes take effect on the **next join / next message**: a removed
member is denied on reconnect, and a downgrade-to-viewer means subsequent updates
are dropped (the per-connection `can_write` is fixed at join, so a *live* socket
is not proactively kicked/downgraded). An immediate live kick is **not**
implemented in this spec — spec 29 exposes no membership-change pub/sub signal; it
is a candidate for a later refactor.

### 7. `/permissions` endpoint

`GET /api/v1/projects/{id}/permissions` → `{role, capabilities[]}` (requires
`PROJECT_READ`; non-member → 404) drives the frontend gating: a `viewer` role
mounts the collab editor **read-only** (CodeMirror non-editable + `y-codemirror`
not pushing local edits, enforced server-side too) with a **"View only"** banner,
and the Share dialog already hides management controls for non-owners (spec 33).
UI gating is convenience; the server remains authoritative.

## Consequences

- New `authorization/` package (`capabilities`, `service`, `dependencies`) + a
  `compile_allowed_for_viewers` setting. Every project router now imports
  `require_capability`; `tree/documents/files/projects/compile/synctex/logparse`
  dropped their `owned_project` helpers. WS `Connection` gained `can_write`.
- No schema change (the `(project_id, user_id, status)` lookup is covered by
  spec-33 indexes). Frontend: `usePermissions` hook + read-only wiring + banner.
- All prior specs' tests pass through the new guard unchanged (legitimate owner
  access is a strict subset of the matrix). 59 new backend tests (matrix,
  REST role-matrix, WS viewer/non-member, permissions) + frontend permission/
  banner tests.
