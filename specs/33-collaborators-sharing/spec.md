# Spec 33 — Collaborators & sharing (requirements)

## 1. Summary

This spec introduces the sharing model: a project owner invites people by email
with a role (`owner` / `editor` / `viewer`), invitees accept or decline, and the
owner can list collaborators, change a role, remove a collaborator, leave a
project, or transfer ownership. It adds two tables (`project_memberships`,
`project_invites`), REST endpoints under `/api/v1/projects/{id}/members` and
`/invites`, an async-stubbed invite-email hook, and a shadcn/ui "Share" modal.
Role *enforcement* across all surfaces is spec 34; here we store and manage the
sharing state.

## 2. Context & dependencies

- **Depends on:**
  - **Spec 11** — `projects` table with an owner (`owner_id` / `user_id`) and the
    project CRUD/ownership model this builds on.
  - **Spec 32 / 31** — collaborators editing the same document live; sharing
    decides *who* may be those collaborators.
  - **Spec 06** — `users` table (lookup invitee by email; resolve members).
  - **Spec 08** — `current_user` dependency for authenticating the actor.
  - **Spec 03** — async SQLAlchemy session + Alembic migrations.
- **Unlocks:**
  - **Spec 34** — central authorization reads `project_memberships` to decide
    capability across REST/WS/compile.
  - **Spec 39** — replaces the stubbed invite-email job with real email + in-app
    notifications.
- **Affected areas:** backend (models, migration, schemas, service, router, ARQ
  job stub), frontend (Share modal + API client), docs.

## 3. Goals

- Persist project membership with a role and status.
- Persist pending invites keyed by an opaque token, addressed by email, with a
  role and an expiry.
- Invite flow: owner invites by email → invite row created (status `pending`) →
  async email job enqueued (stub) → invitee accepts (becomes a member) or
  declines (invite closed).
- Manage members: list, change role, remove a member, leave (self-remove),
  transfer ownership (exactly one owner at a time).
- Surface all of the above in a "Share" modal in the editor/project UI.
- Be the single source of truth for "who can access this project and as what",
  consumed by spec 34.

## 4. Non-goals (explicitly out of scope)

- **Enforcement** of roles on document/file/compile/WS endpoints — **spec 34**.
  This spec only protects its own `/members` and `/invites` endpoints with the
  minimal owner/self checks needed for correctness.
- Real email delivery — **spec 39**; here the email send is an ARQ job stub that
  records intent (and may log) but sends nothing.
- In-app notifications / notification center — **spec 39**.
- Public/link sharing, "anyone with the link", token-less public access — out of
  scope (Inkstave starts invite-only).
- Organizations/teams/groups — out of scope.

## 5. Detailed requirements

### 5.1 Data model

Two new tables (async SQLAlchemy models + one Alembic migration). Use the
project's established conventions (UUID or bigint PKs as set by spec 03/11,
timezone-aware timestamps, `created_at`/`updated_at`).

**`project_memberships`**

| Column | Type | Constraints |
| --- | --- | --- |
| `id` | PK | per project convention |
| `project_id` | FK → `projects.id` | not null, `ON DELETE CASCADE`, indexed |
| `user_id` | FK → `users.id` | not null, `ON DELETE CASCADE`, indexed |
| `role` | enum(`owner`,`editor`,`viewer`) | not null |
| `status` | enum(`active`,`pending`,`left`) | not null, default `active` |
| `created_at` | timestamptz | not null |
| `updated_at` | timestamptz | not null |

- **Unique constraint** `(project_id, user_id)` — a user has at most one
  membership per project.
- **At most one `owner` per project** — enforce in the service layer (and ideally
  a partial unique index `WHERE role='owner'`). The project's creator (spec 11)
  gets an `owner` active membership; decide whether to backfill existing projects
  in the migration (recommended: data migration creating an `owner` membership
  for each project's existing owner). Record this in the ADR.
- `role='owner'` rows are created only via project creation or ownership
  transfer, never via the invite flow (invites are editor/viewer only).

**`project_invites`**

| Column | Type | Constraints |
| --- | --- | --- |
| `id` | PK | per convention |
| `project_id` | FK → `projects.id` | not null, `ON DELETE CASCADE`, indexed |
| `email` | citext/text (case-insensitive) | not null, indexed |
| `role` | enum(`editor`,`viewer`) | not null (no inviting as owner) |
| `token` | text | not null, **unique**, opaque, high-entropy (≥ 32 bytes, urlsafe) |
| `status` | enum(`pending`,`accepted`,`declined`,`revoked`,`expired`) | not null, default `pending` |
| `invited_by` | FK → `users.id` | not null |
| `expires_at` | timestamptz | not null (default now + `INVITE_TTL`, e.g. 14 days) |
| `created_at` | timestamptz | not null |
| `accepted_at` / `responded_at` | timestamptz | nullable |

- **Index** `(project_id, email)` and unique on `token`.
- At most one **pending** invite per `(project_id, lower(email))` — re-inviting an
  already-pending email refreshes/replaces the existing pending invite rather than
  duplicating (service-level; optionally a partial unique index
  `WHERE status='pending'`).
- The token is the bearer secret used in the accept/decline links; store as-is or
  hashed (hashed preferred — store `token_hash`, return raw token only at
  creation/email time). Pick one and document it.

### 5.2 Backend / API

All endpoints require an authenticated user (`current_user`) unless noted.
Base: `/api/v1/projects/{project_id}/members` and
`/api/v1/projects/{project_id}/invites`, plus token-based accept/decline.

Pydantic v2 schemas; standard error envelope from spec 02.

**Members**

| Method | Path | Auth | Body / Query | Response | Codes |
| --- | --- | --- | --- | --- | --- |
| GET | `/projects/{id}/members` | member of project | — | `[{ user_id, name, email, role, status }]` (owner + active members) | 200, 401, 403, 404 |
| PATCH | `/projects/{id}/members/{user_id}` | **owner** only | `{ role: editor\|viewer }` | updated member | 200, 400, 401, 403, 404 |
| DELETE | `/projects/{id}/members/{user_id}` | **owner** (remove other) **or self** (leave) | — | 204 | 204, 401, 403, 404 |
| POST | `/projects/{id}/members/transfer` | **owner** only | `{ to_user_id }` (must be active member) | new ownership | 200, 400, 401, 403, 404 |

- PATCH cannot set role to `owner` (transfer endpoint only) and cannot change the
  current owner's role.
- DELETE on self = "leave"; the owner **cannot** leave without transferring first
  (400 `OWNER_CANNOT_LEAVE`). Removing the last/only owner is impossible.
- Transfer: target becomes `owner`; previous owner is demoted to `editor`
  (default) — atomic in one transaction; document the demotion target.

**Invites**

| Method | Path | Auth | Body | Response | Codes |
| --- | --- | --- | --- | --- | --- |
| GET | `/projects/{id}/invites` | **owner** only | — | list of pending invites | 200, 401, 403, 404 |
| POST | `/projects/{id}/invites` | **owner** only | `{ email, role: editor\|viewer }` | created invite (no raw token in body unless to the inviter is acceptable; never leak to others) | 201, 400, 401, 403, 404, 409 |
| DELETE | `/projects/{id}/invites/{invite_id}` | **owner** only | — | 204 (revoke) | 204, 401, 403, 404 |
| POST | `/invites/{token}/accept` | authenticated; the logged-in user's email **should** match the invite email (see below) | — | `{ project_id, role }` | 200, 400, 401, 403, 404, 410 |
| POST | `/invites/{token}/decline` | authenticated (token bearer) | — | 204 | 204, 401, 404, 410 |
| GET | `/invites/{token}` | authenticated | — | invite preview `{ project_name, inviter_name, role, email }` for the accept screen | 200, 404, 410 |

Invite rules:
- POST invite: reject if the email already belongs to an active member (409
  `ALREADY_MEMBER`); if a pending invite exists for that email, refresh it. The
  invitee may or may not have an account yet — store by email; resolution to a
  `user_id` happens at accept time.
- Accept: requires a logged-in user. **Email match policy:** the authenticated
  user's verified email must equal the invite email (case-insensitive). If a
  user without an account follows the link, they register/log in first (handled by
  existing auth), then accept. On accept: create/activate a `project_memberships`
  row (role from invite, status `active`), set invite `accepted`, set
  `accepted_at`. Accepting an already-member is idempotent (200, no duplicate).
- Expired (`expires_at < now`) or non-pending → 410 `INVITE_EXPIRED` / `GONE`.
- Decline: marks invite `declined`; no membership created.
- Revoke (owner DELETE): marks invite `revoked`.

**Service layer (`backend/.../collaborators/`):**

- `CollaboratorsService` / `SharingService` with methods:
  `list_members`, `change_role`, `remove_member`, `leave`, `transfer_ownership`,
  `create_invite`, `list_invites`, `revoke_invite`, `accept_invite`,
  `decline_invite`, `get_invite_preview`. Pure-ish, transaction-bounded, raising
  typed domain errors mapped to the HTTP codes above.
- A capability helper `is_owner(project, user)` / `membership_of(project, user)`
  used by these endpoints. (The *general* capability matrix is spec 34; here a
  thin owner check suffices and may be superseded by spec 34's service.)

**Email job (stub):**

- An ARQ job `send_project_invite_email(invite_id)` enqueued on invite creation.
  In this spec it is a **stub**: it loads the invite, builds the accept URL
  (`{FRONTEND_URL}/invite/{token}`), logs structured intent, and returns. It must
  be enqueued (so spec 39 only swaps the body) and must be a no-op for delivery.
  In tests, ARQ/Redis is faked and the job is asserted enqueued, not executed
  against a real SMTP.

### 5.3 Frontend / UI

**Share modal (`frontend/src/features/sharing/ShareDialog.tsx`):**

- Triggered by a "Share" button in the editor/project header. shadcn/ui `Dialog`.
- Sections:
  1. **Invite by email**: email input + role `Select` (Editor/Viewer) + "Invite".
     Validates email format; shows inline errors (already member, etc.); on
     success the invite appears in the pending list and a toast confirms.
  2. **People with access**: list of active members with avatar, name, email,
     role. For the owner, each non-owner row has a role `Select` (Editor/Viewer)
     and a "Remove" action; the owner row shows "Owner" with a "Transfer
     ownership" affordance. The current user sees a "Leave project" action
     (disabled/hidden for the owner with an explanatory tooltip).
  3. **Pending invites** (owner only): pending emails with role and a "Revoke".
- Non-owner members see a read-only view (their own membership + the access list)
  without management controls.
- States: loading (skeleton), error (inline + retry), empty pending list message.
- Accessibility: dialog focus trap (shadcn handles), labelled controls,
  destructive actions (remove/revoke/transfer) confirmed via `AlertDialog`.

**Accept-invite page (`/invite/:token`):**

- Fetches the invite preview (`GET /invites/{token}`). Shows project name,
  inviter, role. If not logged in, routes through login/register (existing auth),
  preserving the token. "Accept" / "Decline" buttons call the respective
  endpoints; on accept, navigates into the project; on decline, returns to
  dashboard. Handles 410 (expired/gone) with a clear message.

**API client:** typed functions for every endpoint above in the frontend API
layer (matching spec 09 conventions).

### 5.4 Real-time / jobs / external integrations

- ARQ job `send_project_invite_email(invite_id)` — stub as described in §5.2.
- No WebSocket changes in this spec. (When a collaborator is removed mid-session,
  *kicking* them from the live room is spec 34's enforcement concern; here a
  removed member simply loses future access.)

### 5.5 Configuration

- `.env.example` additions:
  - `INVITE_TTL_DAYS` (default `14`).
  - `FRONTEND_URL` (if not already present from earlier specs) — base for the
    accept link.
- Email transport config is **not** added here (spec 39).

## 6. Overleaf reference (study only — never copy)

> Learn the sharing model and flows; write Inkstave's own (different schema,
> CRDT-based collaboration, JWT auth). Never copy code.

- `services/web/app/src/Features/Collaborators/CollaboratorsController.mjs` —
  endpoint surface for listing/removing collaborators, transfer, leave. Learn
  the *operations* and their authorization expectations.
- `services/web/app/src/Features/Collaborators/CollaboratorsInviteController.mjs`
  and `CollaboratorsInviteHandler.mjs` — the invite-by-email lifecycle: create,
  token, resend, accept, revoke, expiry. Study the *flow*, not the code.
- `services/web/app/src/Features/Collaborators/CollaboratorsInviteHelper.mjs` —
  token generation/handling concerns (hashing, secrecy). Implement your own.
- `services/web/app/src/Features/Collaborators/CollaboratorsGetter.mjs` — how
  members and their privilege levels are resolved for a project.
- `services/web/app/src/Features/Collaborators/CollaboratorsHandler.mjs` and
  `OwnershipTransferHandler.mjs` — add/remove members, transfer ownership rules
  (single owner, demotion of previous owner).
- `services/web/app/src/Features/Collaborators/CollaboratorsEmailHandler.mjs` —
  what the invite email contains; informs the stub's payload (full send in 39).
- `services/web/app/src/models/ProjectInvite.mjs` — fields on an invite (email,
  privileges, token, expiry). Inkstave's `project_invites` is an independent
  design.

## 7. Acceptance criteria

1. **Given** an owner, **when** they POST an invite for an email with role
   `editor`, **then** a `pending` `project_invites` row is created, the
   invite-email ARQ job is enqueued, and the invite appears in `GET .../invites`.
2. **Given** a logged-in user whose email matches a pending invite, **when** they
   POST `/invites/{token}/accept`, **then** an `active` membership with the
   invited role is created and the invite is marked `accepted`; repeating the call
   is idempotent.
3. **Given** an invite, **when** the invitee POSTs `/invites/{token}/decline`,
   **then** the invite is `declined` and no membership exists.
4. **Given** an expired invite, **when** accept/decline is attempted, **then** the
   API returns 410 and no membership is created.
5. **Given** an owner, **when** they PATCH a member's role to `viewer`, **then**
   `GET .../members` reflects the new role; attempting to PATCH a role to `owner`
   returns 400.
6. **Given** an owner, **when** they DELETE another member, **then** that
   membership is removed (or marked `left`) and the user no longer appears in
   `members`.
7. **Given** the owner, **when** they attempt to leave (DELETE self) without
   transferring, **then** the API returns 400 `OWNER_CANNOT_LEAVE`.
8. **Given** an owner, **when** they POST `/members/transfer` to an active member,
   **then** that member becomes the sole `owner` and the previous owner is demoted
   in a single transaction; there is never more than one owner.
9. **Given** a non-owner member, **when** they call any owner-only endpoint
   (invite/revoke/change-role/remove-other/transfer), **then** the API returns 403.
10. **Given** an email that is already an active member, **when** the owner
    invites it, **then** the API returns 409 `ALREADY_MEMBER`.
11. **Given** the Share modal opened by an owner, **then** they can invite,
    change roles, remove members, revoke invites and transfer ownership; a
    non-owner sees a read-only access list plus their own "Leave" action.

## 8. Test plan

> Keep the full suite under 2 minutes. Backend tests use the test DB + faked
> Redis/ARQ (no real SMTP). Frontend uses Vitest + RTL with a mocked API client.

- **Unit (pytest):**
  - Service methods: role transitions, single-owner invariant, transfer demotion,
    invite expiry computation, "refresh existing pending invite" logic, token
    generation entropy/uniqueness, email-match policy on accept.
  - Schema validation: invite role limited to editor/viewer; PATCH role excludes
    owner.
- **Integration (pytest + httpx + test DB + fake Redis):**
  - Full invite lifecycle: create → job enqueued (asserted) → accept → membership
    (AC 1–2); decline (AC 3); expired (AC 4); revoke; re-invite refresh.
  - Member management: list, change-role, remove, leave guard for owner (AC 5–7),
    transfer ownership atomicity and single-owner invariant (AC 8).
  - Authz of the sharing endpoints themselves: non-owner → 403 (AC 9);
    already-member → 409 (AC 10); cross-project isolation (member of project X
    cannot manage project Y).
  - Migration smoke: tables created; existing project owner backfilled to an
    `owner` membership.
- **Unit (Vitest):**
  - `ShareDialog`: owner vs non-owner rendering, invite validation, optimistic
    list updates, confirm dialogs for destructive actions (AC 11), error toasts.
  - Accept-invite page: preview render, accept/decline calls, 410 handling.
- **E2E (Playwright):** not required at this stage (sharing flow is covered by
  integration + component tests). The end-to-end invite→collaborate flow is
  exercised holistically in the spec 54 e2e suite.
- **Performance/budget note:** no email, no real Redis, no compile. All tests are
  fast DB/HTTP/component tests; the email job is stubbed and only its enqueue is
  asserted.

## 9. Definition of Done

- [ ] All requirements in §5 implemented (two tables + migration with backfill,
      members + invites endpoints, service layer, stubbed email ARQ job, Share
      modal + accept-invite page + API client).
- [ ] All acceptance criteria in §7 pass.
- [ ] All tests in §8 written and green.
- [ ] Full suite runs in < 2 minutes.
- [ ] Lint/format/type-check clean (ruff + mypy/pyright; ESLint/Prettier; TS strict).
- [ ] `INVITE_TTL_DAYS` (and `FRONTEND_URL` if new) documented in `.env.example`;
      ADR in `docs/` (token hashing choice, single-owner enforcement, owner-leave
      rule, backfill migration).
- [ ] No Overleaf code copied.
