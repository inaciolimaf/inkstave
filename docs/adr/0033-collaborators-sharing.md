# ADR 0033 — Collaborators & sharing: model, tokens, ownership rules

- **Status:** Accepted
- **Date:** 2026-06-10
- **Context spec:** 33 — Collaborators & sharing

## Context

Inkstave needs a sharing model: a project owner invites people by email with a
role, invitees accept/decline, and the owner manages members and ownership. This
ADR records the schema and policy decisions; role *enforcement* across
REST/WS/compile is spec 34, which reads `project_memberships` as the source of
truth.

## Decisions

### 1. Two tables; membership is the source of truth

`project_memberships (project_id, user_id, role, status)` with `UNIQUE
(project_id, user_id)` and a **partial unique index `WHERE role='owner'`** — at
most one owner per project, enforced at both the DB and service layers.
`project_invites (project_id, email, role, token_hash, status, invited_by,
expires_at, …)`.

The project creator gets an `owner` active membership. **Backfill:** the migration
creates an `owner` membership for every existing live project's `owner_id`
(`ON CONFLICT DO NOTHING`), and `create_project` (spec 11) now inserts the owner
membership in the same transaction — so the membership table is authoritative
going forward.

### 2. Invite tokens are hashed at rest

The bearer token is `secrets.token_urlsafe(32)` (≥ 32 bytes entropy). We store
**`token_hash` = SHA-256(raw)**, never the raw token; lookups hash the presented
token. The raw token is returned **only** in the create-invite response (to the
inviter, which the spec permits) and never leaked in any list. Hashing limits the
blast radius of a DB read. Consequence for the email: because the raw token is not
persisted, the spec-33 email job is a **stub** that records intent without the
token-bearing URL; spec 39 (real delivery) will assemble the accept link from the
raw token at send time.

### 3. Single owner; ownership transfer demotes to editor

PATCH role cannot set `owner` (returns **400**, not 422 — `MemberRoleUpdate.role`
is a plain string validated in the service so the domain error surfaces) and
cannot change the current owner's role. The **transfer** endpoint is the only path
to `owner`: it demotes the previous owner to **`editor`** (documented target) and
promotes the target in one transaction, flushing the demote before the promote so
the one-owner partial index is never transiently violated. It also updates
`projects.owner_id`.

### 4. Owner cannot leave; removal is a soft "left"

DELETE-self is "leave"; the owner cannot leave without transferring first (**400
`OWNER_CANNOT_LEAVE`**) — the last owner can never be removed. Removed/left
members are marked `status='left'` (not hard-deleted), so a re-invited user
reactivates the same `(project, user)` row on accept (no unique-constraint clash).
`list_members` returns only `active` members.

### 5. Access policy (mirrors ADR 0007)

A user who is **not a member** of a project sees **404** on its sharing endpoints
(existence is not leaked); a **member who is not the owner** gets **403** on
owner-only operations. Listing members is allowed to any active member.

### 6. Invite acceptance

Accept requires a logged-in user whose email (case-insensitive) **matches** the
invite email (else **403**). It creates/reactivates an active membership with the
invited role, marks the invite `accepted`, and is **idempotent** (re-accepting an
active membership returns 200). Expired (`expires_at < now`) or non-pending
invites return **410**. Decline marks `declined` (token bearer, no email match);
revoke (owner) marks `revoked`. Re-inviting a still-pending email **refreshes** the
existing row (new token + expiry) rather than duplicating — guarded by a partial
unique index `WHERE status='pending'` on `(project_id, email)`.

### 7. Email job is an enqueued stub

`send_project_invite_email(invite_id)` is registered on the existing compile ARQ
worker/queue (one worker for spec 33; a dedicated queue is a spec-39 concern) and
**enqueued on invite creation**. It loads the invite, logs structured intent, and
sends nothing. Tests assert the enqueue (via a faked enqueuer) and call the job
directly to verify it is a harmless no-op.

## Consequences

- New models `ProjectMembership` / `ProjectInvite`, migration
  `a1c2e3f40915` (tables + indexes + owner backfill), `services/sharing.py`,
  `schemas/sharing.py`, `api/routes/sharing.py` (members + invites + token
  routes), `sharing/jobs.py` + `sharing/enqueuer.py`, and a `GoneError` (410) in
  `errors.py`. `create_project` now also creates the owner membership.
- New settings `FRONTEND_URL`, `INVITE_TTL_DAYS` (documented in `.env.example`).
- Frontend: `features/sharing/` (typed API, `ShareDialog`, `AcceptInvitePage` at
  `/invite/:token`), a Share button in the editor, and the shadcn `Avatar`/`Card`
  reuse. Role enforcement on documents/compile/WS is **deferred to spec 34**;
  removing a member here only revokes *future* access (no live-room kick yet).
