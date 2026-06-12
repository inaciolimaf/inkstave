# Spec 34 — Access control (centralized authorization) (requirements)

## 1. Summary

This spec centralizes authorization. It defines one authorization service and a
role→capability matrix derived from spec-33 memberships, then enforces it
**consistently** across three surfaces: REST endpoints (project, document, file),
the spec-29 collaboration WebSocket (join the room only if you are a member;
viewers get a read-only Yjs binding and server-side write rejection), and compile
(members only). Guards are retrofitted onto the earlier endpoints so that, after
this spec, no project surface is reachable without the correct role. 403 (and
404-for-non-members) semantics are standardized.

## 2. Context & dependencies

- **Depends on:**
  - **Spec 33** — `project_memberships` (role owner/editor/viewer, status active)
    is the authority for "who may do what". This spec reads it; it does not change it.
  - **Spec 29** — the collab WebSocket and its room-join handshake; this spec adds
    the authorization gate at join and the viewer write-rejection.
  - **Spec 28** — the server CRDT applies updates; this spec ensures viewer
    updates are rejected before they are applied/persisted/broadcast.
  - **Spec 22** — compile API + ARQ compile job; gated to members here.
  - **Specs 11–14** — project/file/doc/binary REST endpoints whose ad-hoc
    owner-only checks (if any) are replaced by the central guard.
  - **Spec 31/32** — frontend binding/presence; this spec plumbs a real
    `readOnly` capability into the spec-31 binding.
  - **Spec 08** — `current_user` dependency; this spec composes on top of it.
- **Unlocks:** all later collaborative/compile features can assume authorization
  is uniformly enforced; spec 35 refactors the whole collaboration surface.
- **Affected areas:** backend (authorization module + retrofits across routers,
  WS, compile/job), frontend (read-only editor wiring, capability-aware UI),
  docs (capability matrix ADR).

## 3. Goals

- One **authorization service** (`AuthorizationService` / `authz`) that, given a
  user and a project, returns the user's effective role and a set of capabilities,
  with a single function to assert a required capability (raising a typed
  forbidden error otherwise).
- A documented **role → capability matrix** (owner/editor/viewer + non-member).
- A reusable **FastAPI dependency** (e.g. `require_capability(cap)` /
  `require_project_role(...)`) that loads membership once per request and is
  applied to every project-scoped REST route.
- **WebSocket gate:** spec-29 room join verifies membership; non-members are
  rejected (close with a defined code); viewers join in read-only mode.
- **Viewer read-only on the CRDT:** the server rejects/drops Yjs `update` messages
  from viewer connections (they may still receive sync/updates and awareness), so
  a viewer cannot mutate the shared document even by crafting raw messages. The
  client (spec 31) is also set read-only, but the server is the real boundary.
- **Compile gate:** only active members may trigger or read a project's compile.
- **Retrofit** the central guard onto existing project/doc/file endpoints,
  removing scattered/ad-hoc checks.
- Standardize **error semantics**: not-a-member of a private project → 404
  (don't leak existence) for top-level project reads; member-but-insufficient-role
  → 403; unauthenticated → 401. Define precisely (see §5.2).

## 4. Non-goals (explicitly out of scope)

- Admin panel, site administrators, superuser/impersonation roles — out of scope.
- Public/link sharing, anonymous/read-only-public access — out of scope.
- Changing the sharing model, invites, or roles themselves — **spec 33**.
- Per-file / per-folder granular ACLs — roles are project-wide.
- Rate limiting / abuse controls — **spec 52**.
- Audit logging of authorization decisions — beyond minimal structured logs;
  full observability is **spec 51**.

## 5. Detailed requirements

### 5.1 Data model

No new tables. Reads `project_memberships` (spec 33). May add **indexes** if a hot
lookup `(project_id, user_id, status)` is not already covered — ship as an Alembic
migration if added; otherwise none.

### 5.2 Backend / API

**Capability model (`backend/.../authorization/`):**

Define capabilities (enum), e.g.:
`PROJECT_READ`, `PROJECT_WRITE` (rename/settings), `PROJECT_DELETE`,
`PROJECT_SHARE` (manage members/invites), `DOC_READ`, `DOC_WRITE`,
`FILE_READ`, `FILE_WRITE` (upload/delete), `COMPILE`, `COLLAB_READ`,
`COLLAB_WRITE`.

**Role → capability matrix (authoritative):**

| Capability | owner | editor | viewer | non-member |
| --- | :---: | :---: | :---: | :---: |
| `PROJECT_READ` | ✓ | ✓ | ✓ | ✗ |
| `PROJECT_WRITE` (rename/settings) | ✓ | ✗ | ✗ | ✗ |
| `PROJECT_DELETE` | ✓ | ✗ | ✗ | ✗ |
| `PROJECT_SHARE` (members/invites/transfer) | ✓ | ✗ | ✗ | ✗ |
| `DOC_READ` / `FILE_READ` | ✓ | ✓ | ✓ | ✗ |
| `DOC_WRITE` / `FILE_WRITE` (create/edit/move/delete docs, files, tree) | ✓ | ✓ | ✗ | ✗ |
| `COLLAB_READ` (join WS room, receive sync/awareness) | ✓ | ✓ | ✓ | ✗ |
| `COLLAB_WRITE` (send Yjs `update`) | ✓ | ✓ | ✗ | ✗ |
| `COMPILE` | ✓ | ✓ | ✓* | ✗ |

\* Compile for viewers: **viewers MAY compile** (read-only users still need the
PDF). If a stricter policy is desired, make it editor+; default here is
viewer-allowed `COMPILE`. State the chosen default in the ADR. (Project settings
that *change* compile config remain `PROJECT_WRITE`.)

This matrix must live in one place (a dict/table) and be the single source the
service consults. Spec 33's owner-only checks on `/members` and `/invites` are
re-expressed as `PROJECT_SHARE`.

**Authorization service:**

```python
class AuthorizationService:
    async def get_role(self, user_id, project_id) -> Role | None  # None = non-member
    async def get_capabilities(self, user_id, project_id) -> set[Capability]
    async def authorize(self, user_id, project_id, cap: Capability) -> None
        # raises ForbiddenError / NotFoundError per the semantics below
    async def can(self, user_id, project_id, cap: Capability) -> bool
```

- One membership lookup per request, cached on the request state to avoid
  duplicate DB hits when multiple capabilities are checked.
- The project owner is always derived from an `owner` active membership (spec 33).

**Error semantics (standardized):**

- Unauthenticated → **401** (handled by spec-08 auth dependency, before authz).
- Authenticated **non-member** accessing a project resource:
  - For the **top-level project resource and its existence-revealing reads** →
    **404** (do not disclose that the project exists).
  - For sub-resources where 404 vs 403 doesn't leak more than the project read
    already would, returning 404 consistently is acceptable; pick **404 for
    non-members** uniformly to avoid leaks, and document it.
- Authenticated **member with insufficient role** (e.g. viewer attempting a
  write) → **403** with code `INSUFFICIENT_ROLE`.
- WebSocket: non-member join → close with an application close code (e.g. 4403)
  and no room membership; viewer write attempt → message dropped + optional
  `error` frame, connection not necessarily closed (document the choice).

**FastAPI dependency (retrofit point):**

- `require_capability(cap: Capability)` returns a dependency that resolves
  `current_user`, extracts `project_id` from the path, calls
  `authz.authorize(...)`, and yields the membership/role for handler use.
- Apply to **every** project-scoped route:
  - Project CRUD (spec 11): read=`PROJECT_READ`, rename/settings=`PROJECT_WRITE`,
    delete=`PROJECT_DELETE`.
  - File tree (spec 12) + document content (spec 13) + binary files (spec 14):
    reads=`*_READ`, mutations=`*_WRITE`.
  - Members/invites (spec 33): `PROJECT_SHARE` (replacing its local owner checks).
  - Compile (spec 22): trigger/status/output reads=`COMPILE` (+ membership).
- Remove now-redundant ad-hoc ownership checks in those handlers; the dependency
  is the single gate. Where a handler legitimately needs finer logic, it calls
  `authz.authorize`/`can` explicitly rather than re-querying memberships.

**WebSocket gate (spec-29 integration):**

- At room join, resolve the JWT's user, then `authz.get_role(user, project)`:
  - non-member → reject/close (4403); never added to the room.
  - viewer → join with a connection flag `can_write = False`.
  - editor/owner → `can_write = True`.
- On receiving a Yjs `update` (or sync-step-2 carrying an update) from a
  `can_write = False` connection: **drop it** — do not apply to the pycrdt doc,
  do not persist, do not broadcast. Optionally send an `error`/`read_only` frame.
  Awareness and inbound sync/receipt remain allowed for viewers (they see live
  edits and presence).
- **Mid-session revocation:** if a member is removed or downgraded (spec 33) while
  connected, the next join is denied and, for a downgrade to viewer, new updates
  are dropped. Proactive disconnect/downgrade of a live socket on membership
  change is **best-effort** (e.g. via a pub/sub signal if spec 29 provides one) —
  define the minimum: at minimum, the change takes effect on the next message/
  reconnect; document whether immediate kick is implemented.

**Compile gate (spec-22 integration):**

- The compile-trigger endpoint and the compile ARQ job entry both verify
  `COMPILE` + membership for the requesting user. Output retrieval (PDF/log/
  synctex, spec 23) requires `PROJECT_READ`/`COMPILE`. A non-member cannot enqueue
  or read another project's compile.

### 5.3 Frontend / UI

- **Plumb a real `readOnly` into spec 31's binding.** The project/editor bootstrap
  fetches the current user's role (from `GET /projects/{id}/members` self-entry,
  or a dedicated `GET /projects/{id}/me`-style capability endpoint — add a small
  `GET /api/v1/projects/{id}/permissions` returning the user's role +
  capabilities, which the frontend uses). Viewer → editor mounted read-only (CM
  `EditorState.readOnly` + `y-codemirror.next` not pushing local edits).
- **Capability-aware UI:** hide/disable controls the user can't use — viewers see
  no "Share" management controls (consistent with spec 33), no file-tree mutation
  actions (create/rename/delete/move), no doc-editing affordances; editors see
  everything except owner-only (delete project, manage members, transfer).
  Server remains the real boundary; UI gating is convenience only.
- A clear read-only banner/badge in the editor for viewers ("View only").
- 403/404 from the API surfaces a friendly "You don't have access" / "Not found"
  state rather than a raw error.

**New endpoint:** `GET /api/v1/projects/{id}/permissions` → `{ role, capabilities: string[] }`
(requires `PROJECT_READ`; non-member → 404). Drives the frontend gating.

### 5.4 Real-time / jobs / external integrations

- WebSocket join gate + viewer write-rejection as in §5.2.
- Compile job + endpoint gate as in §5.2.
- No new ARQ jobs. No external services.

### 5.5 Configuration

- `COMPILE_ALLOWED_FOR_VIEWERS` (default `true`) — feature flag for the viewer
  compile policy noted in the matrix; documented in `.env.example`.
- No other new env vars.

## 6. Overleaf reference (study only — never copy)

> Learn the centralized-authorization approach; implement independently.

- `services/web/app/src/Features/Authorization/AuthorizationManager.mjs` — a
  single manager that answers "can this user read/write/admin this project",
  resolving the user's privilege level. Learn the *shape* of one central
  decision point.
- `services/web/app/src/Features/Authorization/AuthorizationMiddleware.mjs` — how
  authorization is applied uniformly as middleware on routes (the retrofit idea).
  Inkstave uses a FastAPI dependency instead.
- `services/web/app/src/Features/Authorization/PrivilegeLevels.mjs` and
  `PublicAccessLevels.mjs` — the enumerated privilege levels
  (owner/readAndWrite/readOnly) and how they map to capabilities. Informs
  Inkstave's role→capability matrix (Inkstave omits public access).
- `services/web/app/src/Features/Authorization/PermissionsManager.mjs` /
  `PermissionsController.mjs` — capability/permission checking patterns.
- `services/real-time/app/js/AuthorizationManager.js` and
  `WebsocketController.js` — how the realtime layer checks that a socket may join
  a project and whether it may send document updates (read-only enforcement).
  This directly informs the WS join gate and viewer write-rejection (implement
  for Yjs/pycrdt, not OT).

## 7. Acceptance criteria

1. **Given** a non-member, **when** they GET/PATCH/DELETE any project, doc, file,
   compile, or members endpoint of that project, **then** they receive 404 (for
   project-existence-revealing routes) or 403/404 per the standardized rule — and
   never the underlying data.
2. **Given** a viewer, **when** they perform any write (edit/create/move/delete a
   doc or file, rename project, manage sharing), **then** the API returns 403
   `INSUFFICIENT_ROLE` and no mutation occurs.
3. **Given** a viewer, **when** they GET a document, file, or compile output,
   **then** they succeed (read access).
4. **Given** an editor, **when** they perform doc/file writes and compile, **then**
   they succeed; **when** they attempt to delete the project, manage members, or
   transfer ownership, **then** the API returns 403.
5. **Given** an owner, **then** every capability in the matrix succeeds.
6. **Given** the collaboration WebSocket, **when** a non-member tries to join the
   room, **then** the connection is rejected (close 4403) and they receive no doc
   sync or awareness.
7. **Given** a viewer connected to the WS, **when** they send a Yjs `update`,
   **then** the server drops it: the pycrdt document is unchanged, nothing is
   persisted, and no other client receives that update — while the viewer still
   receives others' edits and awareness.
8. **Given** an editor connected to the WS, **then** their updates apply,
   persist, and broadcast as before (no regression to spec 29/31).
9. **Given** a non-member, **when** they trigger or read a compile, **then** it is
   denied; **given** a member, compile works (no regression to spec 22).
10. **Given** the frontend, **when** a viewer opens the project, **then** the
    editor is read-only with a "View only" banner and mutation controls are
    hidden/disabled; `GET /projects/{id}/permissions` reflects the viewer role.
11. **Given** existing endpoints from specs 11–14/22/33, **then** their previous
    ad-hoc access checks are replaced by the central guard and all their prior
    tests still pass (no behavioural regression for legitimate access).

## 8. Test plan

> Keep the full suite under 2 minutes. Backend tests use the test DB + faked
> Redis/ARQ. WS tests use an in-process test client against the spec-29 server;
> viewer write-rejection is asserted in-process (no real browser needed).

- **Unit (pytest):**
  - The capability matrix: role→capabilities mapping is exhaustive and matches
    §5.2 (table-driven test over every (role, capability) pair).
  - `AuthorizationService.authorize` raises Forbidden/NotFound per semantics;
    request-scoped caching does one membership lookup.
- **Integration (pytest + httpx + test DB):**
  - Parametrized matrix test hitting representative REST endpoints
    (project read/write/delete, doc read/write, file write, members/share,
    compile, permissions) as owner/editor/viewer/non-member, asserting the
    expected 200/403/404 (AC 1–5, 9, 11).
  - `GET /projects/{id}/permissions` returns correct role+capabilities per role.
  - Regression: re-run (or assert still-green) prior project/doc/file/compile
    tests pass through the new guard for legitimate roles (AC 11).
  - WebSocket (in-process spec-29 client): non-member join rejected (AC 6);
    viewer update dropped — doc state/persistence/broadcast unchanged, viewer
    still receives others' updates (AC 7); editor update applies and broadcasts
    (AC 8). Reuse the spec-31 two-in-process-client harness.
- **Unit (Vitest):**
  - Editor read-only wiring for viewer role (CM read-only + no local Yjs writes);
    capability-gated controls hidden for viewer/editor as specified (AC 10),
    using a mocked permissions response.
- **E2E (Playwright):** not required here; the holistic role-restricted flow is
  covered by the spec 54 e2e suite. Keep budget for integration coverage.
- **Performance/budget note:** all authz checks are pure DB lookups; WS tests run
  in-process; no compile/LLM executed. The matrix tests are table-driven and fast.

## 9. Definition of Done

- [ ] All requirements in §5 implemented (authorization service + matrix,
      `require_capability` dependency applied to all project-scoped REST routes,
      WS join gate + viewer write-rejection, compile gate, `/permissions`
      endpoint, frontend read-only + gating).
- [ ] All acceptance criteria in §7 pass.
- [ ] All tests in §8 written and green; prior specs' tests remain green.
- [ ] Full suite runs in < 2 minutes.
- [ ] Lint/format/type-check clean.
- [ ] `COMPILE_ALLOWED_FOR_VIEWERS` documented in `.env.example`; ADR in `docs/`
      capturing the matrix, the 404-vs-403 leak policy, the viewer-compile
      default, and the mid-session-revocation behaviour.
- [ ] No Overleaf code copied.
