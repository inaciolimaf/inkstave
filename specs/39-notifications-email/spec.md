# Spec 39 — Notifications & Email (requirements)

## 1. Summary

This spec delivers two related capabilities: (1) **async email** via a pluggable
sender — SMTP in production, a console/file sender in dev and tests — with all
sends dispatched through ARQ jobs so requests never block, covering invite emails
(spec 33) and password-reset *groundwork*; and (2) **in-app notifications** — a
`notifications` table, endpoints to list / mark-read / dismiss, surfacing of
project invites, and a frontend notifications bell built with shadcn/ui. Email is
mocked in tests; the suite stays fast.

## 2. Context & dependencies

- **Depends on:**
  - **Spec 33** — collaborators & sharing: the invite flow that this spec hooks into
    to (a) create an in-app notification for the invitee and (b) enqueue an invite email.
  - **Spec 04** — testing foundation: ARQ test harness/fixtures, fake Redis, the
    2-minute budget conventions, and the pattern for mocking jobs.
  - **Spec 02/03** — settings object and DB/migration foundation.
  - **Spec 06/07/08** — user model and the current-user auth dependency (notifications
    are per-user; endpoints require auth).
- **Unlocks:** a reusable email-job + notification system later specs (password reset in
  settings, agent/compile notifications) build on.
- **Affected areas:** backend (email sender abstraction, ARQ email jobs, notifications
  model + service + endpoints, invite hook), frontend (notifications bell + API), infra
  (.env SMTP config), docs (ADR).

## 3. Goals

- A `EmailSender` abstraction with at least three implementations: `SmtpEmailSender`
  (default in prod), `ConsoleEmailSender` (logs the rendered email), and
  `FileEmailSender` (writes `.eml`/JSON files to a dir — for local inspection/tests).
  Selected by env; injected via DI.
- An ARQ job that renders a templated email and calls the configured sender. Email is
  **never** sent inline in a request; handlers only enqueue.
- An **invite email** job wired to the spec-33 invite flow.
- **Password-reset groundwork:** a reusable templated email job (subject/body template +
  a placeholder reset URL) that a future spec can trigger — no token issuance/validation
  flow here, just the dispatchable job and template.
- A `notifications` table and a `NotificationService` to create notifications.
- Endpoints to **list** (unread + recent), **mark-read** (one / all), and **dismiss**
  (delete/soft-delete) notifications, scoped to the current user.
- Invite events create an in-app notification surfaced to the invitee.
- A frontend **notifications bell**: unread count badge, dropdown list, mark-read &
  dismiss actions, and a link/action to accept a surfaced invite.
- Notification **TTL/expiry**: expired notifications are not listed and are swept.

## 4. Non-goals (explicitly out of scope)

- Marketing / newsletter / digest email.
- The complete password-reset user flow (token generation, reset form, validation) —
  only the email job/template groundwork.
- Real-time push of notifications over WebSocket (polling/refetch on the bell is enough;
  if a WS presence channel already exists from spec 29 you MAY optionally push a "new
  notification" ping, but it is not required).
- Per-user email preferences / unsubscribe management.

## 5. Detailed requirements

### 5.1 Data model

One new table; one Alembic migration.

#### 5.1.1 `notifications`

| Column | Type | Constraints / notes |
| --- | --- | --- |
| `id` | `uuid` | PK, default `gen_random_uuid()` |
| `user_id` | `uuid` | NOT NULL, FK → `users.id` ON DELETE CASCADE — the recipient |
| `type` | `text` | NOT NULL — enum-like string, e.g. `project_invite`, `generic` (validated app-side) |
| `payload` | `jsonb` | NOT NULL default `'{}'` — type-specific data (e.g. `{project_id, project_name, inviter_name, role, invite_id}`) |
| `read_at` | `timestamptz` | NULLABLE — set when the user marks it read |
| `dismissed_at` | `timestamptz` | NULLABLE — set when dismissed (soft delete; excluded from listing) |
| `expires_at` | `timestamptz` | NULLABLE — when the notification should no longer be shown / is sweepable |
| `created_at` | `timestamptz` | NOT NULL default `now()` |

Indexes:
- Index `ix_notifications_user_active` on `(user_id, created_at DESC)`
  `WHERE dismissed_at IS NULL` — fast listing of active notifications.
- Index `ix_notifications_expiry` on `(expires_at)` `WHERE expires_at IS NOT NULL` — for
  the expiry sweep.

> De-dupe rule: avoid creating duplicate active `project_invite` notifications for the
> same `(user_id, invite_id)` — if one exists and is not dismissed, update it rather than
> insert a second.

### 5.2 Backend / API

#### 5.2.1 Email sender abstraction

Define a protocol/ABC and implementations (module `backend/app/email/`):

```python
@dataclass
class OutgoingEmail:
    to: str
    subject: str
    text_body: str
    html_body: str | None = None
    from_addr: str | None = None      # defaults to EMAIL_FROM

class EmailSender(Protocol):
    async def send(self, email: OutgoingEmail) -> None: ...

class SmtpEmailSender(EmailSender): ...     # uses aiosmtplib / configured SMTP
class ConsoleEmailSender(EmailSender): ...  # logs the rendered email at INFO
class FileEmailSender(EmailSender): ...      # writes one file per email to EMAIL_FILE_DIR
```

- A factory `get_email_sender(settings) -> EmailSender` selects the implementation from
  `EMAIL_BACKEND` (`smtp` | `console` | `file`). Provided via FastAPI/ARQ DI so it can be
  overridden in tests with a capturing fake.
- SMTP sender uses async SMTP (e.g. `aiosmtplib`); honours host/port/user/pass/TLS env.

#### 5.2.2 Email templates

- A small template registry rendering `(subject, text_body, html_body)` from a context.
  Provide at least:
  - `project_invite` — context `{project_name, inviter_name, role, accept_url}`.
  - `password_reset` — context `{user_name, reset_url}` (groundwork; not yet triggered by
    a real flow).
- Templates are plain Python string templates or Jinja2 (if already a dependency); keep
  them in `backend/app/email/templates/`. Subjects and bodies are written by you, not
  copied from Overleaf.

#### 5.2.3 ARQ email jobs

In the worker (`backend/app/jobs/` or established location):

```python
async def send_email_job(ctx, *, template: str, to: str, context: dict) -> dict:
    # renders template -> OutgoingEmail -> get_email_sender(ctx.settings).send(...)
```

- Request handlers/services **enqueue** `send_email_job` (via the ARQ pool); they never
  call `EmailSender.send` directly.
- The job is retry-safe: on transient SMTP failure it raises so ARQ retries per the
  configured retry policy; log a structured error. Idempotency is best-effort (re-sending
  an invite email on retry is acceptable).
- A convenience enqueue helper, e.g. `enqueue_invite_email(pool, *, to, project_name,
  inviter_name, role, accept_url)`.

#### 5.2.4 Notification service

`NotificationService` (module `backend/app/notifications/`):

```python
async def create(*, user_id, type, payload, expires_at=None) -> Notification: ...
async def list_active(*, user_id, limit=50, before=None) -> list[Notification]: ...
async def unread_count(*, user_id) -> int: ...
async def mark_read(*, user_id, notification_id) -> Notification: ...
async def mark_all_read(*, user_id) -> int: ...
async def dismiss(*, user_id, notification_id) -> None: ...
async def sweep_expired(*, now=None) -> int: ...   # used by the ARQ expiry job
```

- `list_active` excludes `dismissed_at IS NOT NULL` and rows past `expires_at`.
- All mutating methods enforce that the notification belongs to `user_id` (else 404).

#### 5.2.5 Endpoints (JWT-authenticated; current user only)

| Method & path | Behaviour | Codes |
| --- | --- | --- |
| `GET /api/notifications` | list active notifications newest-first; query `before`, `limit` (≤100); also returns `unread_count` | 200 |
| `GET /api/notifications/unread-count` | `{ "count": n }` | 200 |
| `POST /api/notifications/{id}/read` | mark one read | 200 / 404 |
| `POST /api/notifications/read-all` | mark all the user's active notifications read; returns `{ "updated": n }` | 200 |
| `DELETE /api/notifications/{id}` | dismiss (soft delete) | 204 / 404 |

- All scoped to the authenticated user; a notification belonging to another user → `404`
  (no leak). Response schema mirrors the table (no internal columns leaked beyond the
  fields above; `payload` is returned as-is).

#### 5.2.6 Invite hook (spec 33 integration)

- When an invite is created in spec 33's flow, this spec's hook:
  1. Resolves whether the invitee email maps to an existing user. If yes, create a
     `project_invite` notification for that user (with de-dupe per §5.1.1) carrying
     `{project_id, project_name, inviter_name, role, invite_id, accept_url}`, with an
     `expires_at` derived from `NOTIFICATION_INVITE_TTL_DAYS`.
  2. **Always** enqueue `send_email_job` with the `project_invite` template to the invitee
     email (existing user or not).
- Wire this without changing spec-33's public invite contract (the hook is additive). If
  spec 33 already emitted an event/signal, subscribe to it; otherwise call the hook from
  the invite service.

### 5.3 Frontend / UI

Under the established frontend layout (e.g. `frontend/src/features/notifications/`).

- **NotificationsBell** in the top app bar (shadcn `Button` + `Popover`/`DropdownMenu`):
  - Shows an unread-count `Badge` (from `GET /api/notifications/unread-count`), polled on
    an interval (configurable, default 60s) and refetched when the dropdown opens.
  - Dropdown lists active notifications (newest first) using shadcn list/`Card` styling:
    each shows an icon by `type`, a human message (e.g. "Alice invited you to *Project X*
    as editor"), relative time, and per-item actions.
  - **Mark read**: opening/clicking an item marks it read (calls the read endpoint, clears
    its unread styling). A "Mark all read" action calls `read-all`.
  - **Dismiss**: an × removes the item (calls DELETE; optimistic with rollback on error).
  - For `project_invite`, an **Accept** action navigates to / triggers the spec-33 invite
    acceptance using `payload.invite_id`/`accept_url`, then dismisses or refreshes.
  - Empty state ("You're all caught up"), loading skeleton, and error/retry state.
- Add typed API client methods + TS types for all §5.2.5 endpoints.
- Accessibility: bell button has an aria-label with the unread count; dropdown is keyboard
  navigable (shadcn defaults).

### 5.4 Real-time / jobs / integrations

- **Email** is exclusively via the `send_email_job` ARQ job (§5.2.3). No synchronous sends.
- **Expiry sweep** ARQ job `sweep_notifications(ctx)` calls `sweep_expired`; scheduled
  every `NOTIFICATION_SWEEP_INTERVAL_S` (default 3600). The scheduler is **mocked** in
  tests; the job body is invoked directly.
- **Testing rule:** in tests, the email sender is replaced by a capturing fake (records
  `OutgoingEmail`s); the ARQ pool is the test harness from spec 04 (jobs run inline or are
  asserted as enqueued). No real SMTP connection is ever opened in any test tier.

### 5.5 Configuration

Add to `.env.example`:

| Env var | Default | Meaning |
| --- | --- | --- |
| `EMAIL_BACKEND` | `console` | `smtp` \| `console` \| `file` — which sender to use (`console` in dev) |
| `EMAIL_FROM` | `Inkstave <no-reply@inkstave.local>` | Default From header |
| `EMAIL_FILE_DIR` | `./tmp/emails` | Output dir for `FileEmailSender` |
| `SMTP_HOST` | `localhost` | SMTP server host |
| `SMTP_PORT` | `587` | SMTP server port |
| `SMTP_USER` | *(empty)* | SMTP username (empty → no auth) |
| `SMTP_PASSWORD` | *(empty)* | SMTP password |
| `SMTP_USE_TLS` | `true` | Use STARTTLS/TLS |
| `APP_BASE_URL` | `http://localhost` | Base URL used to build `accept_url` / `reset_url` in emails |
| `NOTIFICATION_INVITE_TTL_DAYS` | `30` | TTL for invite notifications |
| `NOTIFICATION_SWEEP_INTERVAL_S` | `3600` | Expiry sweep interval (mocked in tests) |
| `NOTIFICATIONS_POLL_INTERVAL_MS` | `60000` | Frontend bell poll interval |

All backend vars via the spec-02 Pydantic settings; frontend var via the existing
Vite/env config mechanism.

## 6. Overleaf reference (study only — never copy)

> Read these in `../overleaf/` to understand the approach; write your own code/templates.

- `services/notifications/app/js/Notifications.js` and `NotificationsController.ts` — the
  in-app notification CRUD model and TTL/expiry idea; informs §5.1/§5.2.4/§5.2.5.
- `services/web/app/src/Features/Notifications/NotificationsHandler.mjs`,
  `NotificationsBuilder.mjs`, `NotificationsController.mjs` — how notifications are built
  and surfaced to the web app; informs the invite-notification shape (§5.2.6).
- `services/web/app/src/Features/Email/EmailSender.mjs`, `EmailHandler.mjs`,
  `EmailBuilder.mjs` — the pluggable sender + templated-email approach; informs §5.2.1–3.
  (Overleaf sends via its own queue; Inkstave uses ARQ — approach only.)

## 7. Acceptance criteria

1. **Given** `EMAIL_BACKEND=console`/`file`, **when** an email job runs, **then** the
   rendered email is logged / written to `EMAIL_FILE_DIR` and no SMTP connection is opened.
2. **Given** an invite is created (spec 33) for an email that maps to an existing user,
   **when** the hook runs, **then** (a) a `project_invite` notification is created for that
   user with the correct payload and a future `expires_at`, and (b) a `send_email_job` is
   enqueued with the `project_invite` template addressed to the invitee.
3. **Given** an invite for an email with no existing user, **when** the hook runs, **then**
   the invite email job is still enqueued and no notification row is created.
4. **Given** an invite hook runs twice for the same `(user_id, invite_id)`, **then** only
   one active `project_invite` notification exists (de-dupe).
5. **Given** the authenticated user has active notifications, **when** `GET
   /api/notifications` is called, **then** they are returned newest-first excluding
   dismissed and expired ones, with a correct `unread_count`.
6. **Given** a notification, **when** the user POSTs `…/{id}/read`, **then** `read_at` is
   set and the unread count drops; **when** they POST `read-all`, **then** all active
   notifications are read.
7. **Given** a notification, **when** the user DELETEs it, **then** `dismissed_at` is set
   and it no longer appears in the list (204).
8. **Given** a notification belonging to another user, **when** the current user tries to
   read/dismiss it, **then** the API responds `404` (no leak).
9. **Given** notifications past `expires_at`, **when** `sweep_notifications` runs, **then**
   they are removed/hidden and the sweep is safe to re-run.
10. **Given** the SMTP sender and a transient send failure, **when** the email job runs,
    **then** it raises so ARQ can retry and logs a structured error (verified with a
    fake SMTP that fails once — no real network).
11. **Given** the frontend bell, **when** there are unread notifications, **then** the
    badge shows the count, the dropdown lists them, mark-read/dismiss update the UI
    (optimistic, rolling back on error), and an invite's **Accept** triggers the spec-33
    acceptance.
12. **Given** the Alembic migration is applied then downgraded, **then** the
    `notifications` table and both partial indexes are created and cleanly dropped.

## 8. Test plan

> Keep the suite under 2 minutes. Email sending is always via a capturing fake sender;
> no real SMTP in any tier. The sweep scheduler is mocked; the job body is called directly.

- **Unit (pytest):**
  - Sender factory selects the right implementation per `EMAIL_BACKEND` (criterion 1).
  - Template rendering produces expected subject/body for `project_invite` and
    `password_reset` (groundwork) from a context.
  - `send_email_job` calls the injected fake sender with the rendered email; SMTP failure
    path re-raises (criterion 10) using a fake SMTP.
  - `NotificationService`: create/list/mark-read/mark-all/dismiss/sweep, ownership
    enforcement, de-dupe, expiry exclusion (criteria 4, 5, 6, 7, 8, 9).
- **Unit (Vitest + RTL):**
  - NotificationsBell: badge count, list rendering, mark-read & dismiss (optimistic +
    rollback), empty/loading/error states, Accept action calls the invite acceptance
    (criterion 11).
- **Integration (pytest + httpx + test Postgres + fake Redis + ARQ test harness):**
  - All §5.2.5 endpoints incl. cross-user `404` (criteria 5–8).
  - Invite hook: existing-user → notification + email enqueued; unknown-user → email only
    (criteria 2, 3) — assert the job was enqueued and the fake sender captured the email
    when the job is run inline.
  - Alembic upgrade/downgrade round-trip (criterion 12).
- **E2E (Playwright):** optionally one short flow (bell shows an invite notification and
  Accept works) against a stubbed backend; otherwise covered by component + integration
  tests. Keep it fast and deterministic.
- **Performance/budget note:** No real SMTP, no real email I/O over the network; jobs run
  inline in the ARQ test harness; the periodic sweep scheduler is never started in tests.

## 9. Definition of Done

- [ ] All requirements in §5 implemented.
- [ ] All acceptance criteria in §7 pass.
- [ ] All tests in §8 written and green.
- [ ] Full suite runs in < 2 minutes.
- [ ] Lint/format/type-check clean.
- [ ] New env vars documented in `.env.example`; ADR for sender abstraction + notification
      TTL added under `docs/`.
- [ ] Email is only ever sent via ARQ jobs; tests use a capturing fake (no real SMTP).
- [ ] No Overleaf code or templates copied.
