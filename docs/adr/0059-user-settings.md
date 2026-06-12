# ADR 0059 — User settings & profile

**Status:** accepted (spec 59) · **Phase:** 7 — Hardening, packaging & docs

## Context

Signed-in users need to manage their own account: profile, editor preferences,
password, email, and deletion. This records the model + the security choices.

## Data model (additive migration `fda790a9deeb`)

Five nullable/defaulted columns on `users`:

- `avatar_url` (text, nullable) — optional avatar; the UI falls back to initials
  when null. No upload pipeline is built (spec non-goal); the field accepts a
  URL/path.
- `editor_preferences` (JSONB, not null, default `{}`) — `{theme, font_size,
  keymap}`.
- `pending_email` (citext, nullable), `email_change_token_hash` (text, nullable),
  `email_change_expires_at` (timestamptz, nullable) — the email-change staging
  area. Two partial indexes (only rows mid-change are indexed).

## Editor preferences: server-stored, applied live

Preferences live on the account and load with the user (`GET /users/me`), so the
editor opens in the user's theme/font/keymap on any device. The frontend resolves
them into CodeMirror via Compartments — `theme` → `oneDark`/light (with `system`
following the OS), `font_size` → a theme, `keymap` → default / **vim**
(`@replit/codemirror-vim`) / **emacs** (`@replit/codemirror-emacs`). Changing a
preference optimistically updates the cached user, so an open editor reconfigures
**immediately**, then persists with `PUT /users/me/editor-preferences` (server
clamps font size, enums theme/keymap). Line-wrapping stays a local-only toggle.

## Email change: token groundwork, hashes only

`POST /users/me/change-email` re-authenticates with the password, rejects
in-use/own addresses, stores `pending_email` + a **SHA-256 hash** of a random
token + expiry, and enqueues the existing `send_email_job` with a new
`email_change_confirmation` template to the **new** address. The active email is
unchanged until `POST /users/confirm-email-change` (unauthenticated — the
single-use token authorizes it) swaps it in and clears the staging fields.
Expired → 410, invalid/replayed → 400.

## Password change: revoke-all sessions

`POST /users/me/change-password` verifies the current password, applies the
spec-06 policy to the new one, re-hashes (argon2), then **revokes every existing
refresh token** for the user via a new per-user cutoff
(`refresh_user_revoked_at:{id}` in Redis, checked in the refresh flow). Policy:
**all sessions sign out** — the frontend logs the actor out and routes to login.
Simpler and strictly safer than trying to preserve the current session; AC4 only
requires that other sessions are revoked.

## Account deletion: hard delete, cascade

`DELETE /users/me` re-authenticates and **hard-deletes** the row. Owned projects
(and their tree entities, documents, files, history, memberships, invites) cascade
away through existing `ON DELETE CASCADE` FKs; all tokens are revoked (and the
gone user fails every subsequent auth lookup). The deletion dialog requires the
password **and** a typed `DELETE` confirmation. Chosen over soft-delete to avoid
threading a `deleted_at` filter through every query for a single-tenant CE.

## Trade-offs

- **No avatar upload** — initials fallback only (non-goal); the column is ready if
  uploads are added later via the spec-14 storage abstraction.
- **Revoke-all on password change** signs the actor out too; accepted for
  simplicity and security over a fresh-token-mint dance.
- **vim/emacs keymaps** add two small frontend deps; worth it to make the keymap
  preference actually change behavior (AC3).
