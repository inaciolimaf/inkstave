# Spec 59 — User Settings & Profile (requirements)

## 1. Summary

This spec adds user account management and preferences: editing the **profile**
(display name, optional avatar), **changing email** (with confirmation
groundwork), **changing password**, **editor preferences** (theme, font size,
keymap) that persist server-side and apply to CodeMirror, and **account
deletion**. It exposes the backend endpoints and the shadcn-based frontend
settings pages.

## 2. Context & dependencies

- **Depends on:** **06** (User model, registration, argon2), **09** (frontend
  foundation), **07/08** (JWT auth, current-user dependency, protected routes),
  **18** (CodeMirror editor, for applying preferences). Optionally reuses **39**
  (email/notification ARQ plumbing) for the email-change confirmation send.
- **Unlocks:** a complete account experience; **60** audits it for release.
- **Affected areas:** backend (User model additions + migration, endpoints,
  password/email services, optional avatar storage), frontend (settings routes,
  shadcn pages, editor-preference application), `.env.example` (any new vars).

## 3. Goals

- **Profile:** read and update `display_name` and an optional `avatar`.
- **Change email:** start an email change that generates a confirmation token and
  (via ARQ) sends a confirmation to the **new** address; the email only becomes
  active after the token is confirmed (groundwork; send may be stubbed if spec 39
  is absent).
- **Change password:** require the current password, validate the new one, rehash
  with argon2, and invalidate other sessions/refresh tokens where applicable.
- **Editor preferences:** persist `theme`, `font_size`, `keymap` server-side per
  user; expose GET/PUT; the editor reads and applies them to CodeMirror.
- **Account deletion:** the user can delete their own account, with confirmation,
  cascading or anonymizing their data per a defined policy.
- **Frontend:** shadcn settings pages for all of the above, with proper loading/
  error/success states and validation.

## 4. Non-goals (explicitly out of scope)

- Admin-side user management, roles beyond what spec 57 added, billing, teams.
- Full email provider/SMTP integration (only token + send-hook groundwork).
- Two-factor auth, SSO, OAuth logins.
- Avatar image processing/CDN; an optional simple stored image or initials
  fallback is enough (see §5.1).
- Project-level editor settings (only **user-wide** preferences here).

## 5. Detailed requirements

### 5.1 Data model

Extend the `User` model (additive Alembic migration; never edit a released one):

- `display_name` — already exists from spec 06; ensure it is updatable.
- `avatar_url` *(nullable text)* — optional. Either a URL/path to a stored image
  (reusing spec 14 binary storage) **or** left null with the UI showing initials.
  Choosing the initials-fallback-only approach (no upload) is acceptable; if
  uploads are supported, store via the spec-14 abstraction and validate type/size.
- `editor_preferences` *(JSONB, not null, default `{}`)* — holds `theme`
  (enum/string, e.g. `light`|`dark`|`system`), `font_size` (int, bounded e.g.
  10–28), `keymap` (`default`|`vim`|`emacs`). Server validates/clamps values.
- Email-change support: a small `email_change` table **or** columns
  `pending_email` *(citext, nullable)*, `email_change_token_hash` *(text,
  nullable)*, `email_change_expires_at` *(timestamptz, nullable)*. Prefer a
  dedicated table if cleaner; store only a **hash** of the token, never the raw
  token. (Re-use the email-confirmation pattern/column added in spec 06 if it
  exists.)
- Soft vs. hard delete: add `deleted_at` *(timestamptz, nullable)* if a
  soft-delete/anonymize policy is chosen (see §5.2 deletion).

All new columns ship in one additive migration with appropriate indexes
(`pending_email` unique-ish or at least indexed; `email_change_token_hash`
indexed for lookup).

### 5.2 Backend / API

All endpoints require authentication (current-user dependency, spec 08) unless
noted, operate on the **current user only**, and use Pydantic v2 schemas.

- `GET /api/users/me` — returns the current user's profile + preferences
  (`id`, `email`, `display_name`, `avatar_url`, `editor_preferences`,
  `email_confirmed`, `pending_email` if any). (If spec 06/08 already exposes a
  `me` endpoint, extend it rather than duplicate.)
- `PATCH /api/users/me` — update `display_name` and/or `avatar_url`. Validates
  length/format; returns the updated profile. `200`/`422`.
- `PUT /api/users/me/editor-preferences` — body `{theme, font_size, keymap}`;
  validates/clamps; persists; returns the stored preferences. `200`/`422`.
- `POST /api/users/me/change-password` — body `{current_password, new_password}`.
  Verifies `current_password` (argon2), validates `new_password` against the
  password policy from spec 06, rehashes, persists. On success, **revoke other
  refresh tokens/sessions** (per spec 07/08 mechanism) so a compromised session
  cannot persist; keep the current session valid (or require re-login —
  document the choice). `200`; `400/401` on wrong current password; `422` on weak
  new password.
- `POST /api/users/me/change-email` — body `{new_email, current_password}`.
  Requires password re-auth. Validates the new email is well-formed and not
  already in use; sets `pending_email`, generates a random token, stores its
  **hash** + expiry; enqueues an ARQ job to send a confirmation link to the
  **new** address (job may be a stub/no-op if spec 39 absent, but the enqueue +
  token path must exist). Does **not** change the active email yet. `202`.
- `POST /api/users/confirm-email-change` — body `{token}` (or via a tokenized
  link). Looks up by token hash, checks expiry, and if valid **swaps**
  `email` ← `pending_email`, clears the pending fields, sets `email_confirmed` as
  appropriate. `200`; `400/410` on invalid/expired. (This endpoint may be
  unauthenticated if the token alone authorizes the change — document and make
  the token single-use.)
- `DELETE /api/users/me` — body `{password}` (re-auth) and an explicit confirm
  flag. Deletes the account per the **deletion policy**: either hard-delete with
  cascades, or soft-delete/anonymize (`deleted_at`, scrub PII, detach from
  projects). Owned projects: define and document the policy (e.g. transfer to a
  remaining collaborator, or delete projects with no other owner). Revoke all
  tokens/sessions. `204`. Pick one policy, implement it consistently, and record
  it in the ADR.

Services: put email/password logic in dedicated service functions (mirroring the
spec-06 hashing service) so endpoints stay thin and testable.

### 5.3 Frontend / UI

A `/settings` area (protected route) using shadcn/ui, organized into sections
(tabs or a single page with cards):

- **Profile section:** edit `display_name`; avatar shows uploaded image or an
  initials fallback; (optional) avatar upload control. Save button with
  loading/success/error toasts; client-side validation mirroring the server.
- **Account / email section:** display current email; a "Change email" form
  (new email + current password) that, on submit, shows a "confirmation sent to
  <new email>" state and surfaces any `pending_email`.
- **Security / password section:** change-password form (current, new, confirm),
  strength/validation feedback, success toast; on success follow the
  session-revocation behavior chosen in §5.2 (e.g. inform the user other sessions
  were signed out).
- **Editor preferences section:** controls for `theme`, `font_size`, `keymap`
  (shadcn `Select`/slider/radio). Changes persist via the API and **apply live to
  CodeMirror** — the editor (spec 18) reads user preferences (theme extension,
  font-size styling, keymap extension such as `@codemirror/commands` default vs.
  `@replit/codemirror-vim`/emacs keymap) and reconfigures when preferences
  change. Preferences load on app start so the editor opens in the user's chosen
  settings.
- **Danger zone:** account deletion with a typed-confirmation dialog (shadcn
  `AlertDialog`) requiring the password; on success, log out and redirect.
- States: every form has loading, error (field + form level), empty/default, and
  success states; all are keyboard-accessible with labeled inputs.

### 5.4 Real-time / jobs / external integrations

- ARQ job `send_email_change_confirmation(user_id, new_email, token)` — enqueued
  by the change-email endpoint; reuses spec-39 email plumbing if available,
  otherwise a stub that logs/records intent (and is asserted in tests via a fake
  queue). No real SMTP setup in this spec.
- No WebSocket or LLM changes.

### 5.5 Configuration

Add to `.env.example` if introduced:
- `EMAIL_CHANGE_TOKEN_TTL` (e.g. `86400` seconds) — confirmation token lifetime.
- `APP_BASE_URL` (if not already present) — to build confirmation links.
- Avatar storage settings only if uploads are implemented (reuse spec-14 vars).

## 6. Overleaf reference (study only — never copy)

> Read these in `../overleaf/` for the *shape* of the flows. Write Inkstave's own
> implementation. Verify paths before citing.

- `services/web/app/src/Features/User/UserController.mjs` — account-update
  endpoints (profile, settings) request handling shape.
- `services/web/app/src/Features/User/UserUpdater.mjs` — how user fields/settings
  are updated and persisted.
- `services/web/app/src/Features/User/UserDeleter.mjs` — account-deletion flow and
  the considerations around owned data.
- `services/web/app/src/Features/User/UserEmailsConfirmationHandler.mjs` — the
  email-confirmation token pattern (token issue → verify → apply). Inkstave stores
  only token hashes.
- `services/web/frontend/js/features/settings/components/` — settings page
  structure (`account-info-section.tsx`, `password-section.tsx`,
  `emails-section.tsx`, `leave-section.tsx`, `editor-settings/`) — layout/section
  inspiration only; Inkstave uses shadcn/ui.

## 7. Acceptance criteria

1. **Given** a signed-in user, **when** they `PATCH /api/users/me` with a new
   `display_name`, **then** it persists and `GET /api/users/me` returns it.
2. **Given** a signed-in user, **when** they `PUT
   /api/users/me/editor-preferences` with `{theme, font_size, keymap}`, **then**
   valid values persist (out-of-range font size is clamped/`422`) and are returned
   on subsequent reads.
3. **Given** the settings UI, **when** the user changes theme/font-size/keymap,
   **then** the preference is saved **and** the open CodeMirror editor updates
   live (theme, font size, and keymap behavior change), and a reload preserves the
   choice.
4. **Given** a signed-in user, **when** they POST change-password with the correct
   current password and a valid new password, **then** the hash updates, the new
   password works for login, the old one fails, and other sessions/refresh tokens
   are revoked per the chosen policy.
5. **Given** a wrong current password, **when** change-password is attempted,
   **then** it fails (`400/401`) and nothing changes.
6. **Given** a signed-in user, **when** they POST change-email with a valid new
   address and correct password, **then** `pending_email` is set, a hashed token +
   expiry are stored, a confirmation job is enqueued to the new address, and the
   active email is **unchanged** until confirmation.
7. **Given** a valid, unexpired confirmation token, **when** confirm-email-change
   is called, **then** `email` becomes the `pending_email`, pending fields clear,
   and the token cannot be reused; **given** an expired/invalid token, **then** it
   fails (`400/410`).
8. **Given** a change-email to an address already in use, **when** submitted,
   **then** it is rejected (`409/422`) without altering state.
9. **Given** a signed-in user, **when** they `DELETE /api/users/me` with the
   correct password and confirmation, **then** the account is removed/anonymized
   per the documented policy, owned-project handling follows that policy, all
   tokens are revoked, and subsequent authenticated requests fail.
10. **Given** any of these endpoints called **unauthenticated** (except the
    token-authorized confirm-email-change), **then** they return `401`.
11. **Given** the settings pages, **when** rendered, **then** each form exposes
    labeled inputs and loading/error/success states, and the deletion action
    requires an explicit typed/password confirmation.

## 8. Test plan

> Keep within the 2-minute budget: use the httpx app client + test DB + a fake
> ARQ queue; no real email/SMTP, no real LLM.

- **Unit (pytest / Vitest):**
  - Pydantic schema validation: display name bounds, email format, password
    policy reuse (spec 06), preference clamping/enums.
  - Password service: change verifies current hash and rehashes; token service
    hashes tokens and checks expiry; never stores raw tokens.
  - Vitest: settings components render and validate; editor-preference hook maps
    stored prefs → CodeMirror config (theme/font/keymap) correctly.
- **Integration (pytest + httpx + test DB + fake Redis/ARQ):**
  - Full lifecycle per endpoint: `me` read/patch; editor-preferences round-trip;
    change-password (success, wrong-current, session revocation effect);
    change-email (pending set, job enqueued, email unchanged) → confirm (swap,
    single-use, expiry); duplicate-email rejection; account deletion (policy
    effects, token revocation, owned-project handling).
  - Authz: each endpoint returns `401` unauthenticated; users cannot affect
    another user's account.
- **E2E (Playwright):** sign in → open `/settings` → change display name and
  editor theme/font (verify editor reflects it) → change password and confirm
  re-login works → start an email change and see the pending/confirmation state →
  exercise the delete dialog (can stop before final deletion or use a throwaway
  account). Compiles/agent not involved; email send stubbed.
- **Performance/budget note:** all flows use stubbed email and the in-process app
  client; token TTLs are set low in tests; no external services.

## 9. Definition of Done

- [ ] All requirements in §5 implemented (model + migration, endpoints, UI, job).
- [ ] All acceptance criteria in §7 pass.
- [ ] All tests in §8 written and green.
- [ ] Full suite runs in < 2 minutes.
- [ ] Lint/format/type-check clean (backend + frontend).
- [ ] New env vars documented in `.env.example`; ADR added under `docs/`
      (preferences storage/application, email-change model, deletion policy).
- [ ] No Overleaf code copied.
