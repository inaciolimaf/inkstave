# ADR 0039 — Notifications & async email

- **Status:** Accepted
- **Date:** 2026-06-10
- **Context spec:** 39 — Notifications & Email (async via ARQ)

## Context

Spec 33 stubbed invite-email delivery. Spec 39 makes email real (but never inline),
adds in-app notifications, and surfaces invites in a notifications bell. Email must
stay out of the request path and out of real SMTP in tests.

## Decisions

### 1. Pluggable `EmailSender`, selected by env, injected via DI

`inkstave.mailer` defines `OutgoingEmail`, an `EmailSender` Protocol, and three
implementations: `SmtpEmailSender` (aiosmtplib), `ConsoleEmailSender` (logs at INFO),
and `FileEmailSender` (one JSON file per email under `EMAIL_FILE_DIR`).
`get_email_sender(settings)` picks one from `EMAIL_BACKEND` (`smtp|console|file`,
default `console`). The worker builds the sender once at startup and puts it on the
ARQ `ctx`; tests inject a **capturing fake** via `ctx["email_sender"]`, so no test
tier ever opens a socket.

> The package is named `mailer`, not `email`, to avoid shadowing the stdlib `email`
> module the SMTP sender uses.

### 2. Email is *only* sent by `send_email_job` (ARQ)

`send_email_job(ctx, *, template, to, context)` renders a template → `OutgoingEmail`
→ `sender.send(...)`. On a send failure it **re-raises** so ARQ retries (re-sending
on retry is acceptable). Handlers never call `send(...)`; they enqueue via
`EmailEnqueuer.enqueue_email(template, to, context)`. Templates (`project_invite`,
`password_reset` groundwork) live in `mailer/templates.py` as Inkstave's own strings
— the `password_reset` job/template exist but no reset flow triggers them yet.

This **replaces** spec 33's `InviteEnqueuer`/`send_project_invite_email` stub. The
public invite API is unchanged; the change is internal. Crucially, the enqueue now
carries the **full context including `accept_url`** (built from the raw token at
creation time) rather than just `invite_id` — the email job can't rebuild the
accept link because the token is stored hashed.

### 3. `notifications` table + per-user service

One table (id, user_id, type, payload jsonb, read_at, dismissed_at, expires_at,
created_at) with two partial indexes: `(user_id, created_at DESC) WHERE dismissed_at
IS NULL` for listing and `(expires_at) WHERE expires_at IS NOT NULL` for the sweep.
`NotificationService` does create / list_active / unread_count / mark_read /
mark_all_read / dismiss / sweep_expired. **Listing excludes dismissed + expired**;
all mutators enforce ownership (cross-user → 404, no leak). `sweep_notifications`
(hourly ARQ cron, mocked in tests) hard-deletes expired rows and is idempotent.

### 4. Invite hook: notification (existing users only) + always email

`notify_invite` runs additively in the invite route: it creates a `project_invite`
notification **only if the invitee email maps to an existing user** (de-duped per
`(user_id, invite_id)` so a re-invite updates rather than duplicates), and **always**
enqueues the invite email. The notification carries
`{project_id, project_name, inviter_name, role, invite_id, accept_url}` with an
`expires_at` from `NOTIFICATION_INVITE_TTL_DAYS`.

### 5. Frontend bell

`NotificationsBell` (top app bar) polls `unread-count` (`NOTIFICATIONS_POLL_INTERVAL_MS`,
default 60s) for a badge, opens a `Popover` listing active notifications, marks read
(click), dismisses (×), marks all read, and for `project_invite` offers **Accept**
that navigates to the spec-33 accept route derived from `accept_url`. Empty / loading
/ error states included; the bell's aria-label carries the unread count.

## Consequences

- New `inkstave.mailer` + `inkstave.notifications` packages, `notifications` table +
  migration `e5f7b9c13d46`, a notifications router, and the frontend
  `features/notifications/`. `aiosmtplib` added. `get_invite_enqueuer` →
  `get_email_enqueuer`; spec-33 tests updated to the new enqueuer (and the old
  invite-job test removed).
- Tests: email sender/factory/templates + `send_email_job` (incl. retry-on-failure)
  as units; notification service + endpoints + invite hook as integration; the bell
  as Vitest. No real SMTP, no started sweep scheduler, jobs invoked directly.
