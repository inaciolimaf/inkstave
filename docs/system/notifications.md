# Notifications and e-mail

Two delivery paths. The inbox is a per-user list of in-app notifications, shown by the bell in the top
bar. E-mail is rendered and sent by a background job, for invites and for the account link flows. Spec 39
built both; spec 103 hardened the transport and added the Resend backend and `send-test-email`.

## Where it is

| File | Role |
|---|---|
| `backend/src/inkstave/modules/notifications` | Package: exports `notify_invite` |
| `backend/src/inkstave/modules/notifications/models.py` | `Notification`, `NotificationType` |
| `backend/src/inkstave/modules/notifications/routes.py` | Inbox routes |
| `backend/src/inkstave/modules/notifications/schemas.py` | Response models |
| `backend/src/inkstave/modules/notifications/inbox/service.py` | `NotificationService`, `NotificationNotFoundError` |
| `backend/src/inkstave/modules/notifications/inbox/invite_hook.py` | `notify_invite`: inbox row plus invite e-mail |
| `backend/src/inkstave/modules/notifications/inbox/jobs.py` | `sweep_notifications` |
| `backend/src/inkstave/infra/mailer` | Package: senders, templates, enqueuer, job |
| `backend/src/inkstave/infra/mailer/templates.py` | `render_email` and the five templates |
| `backend/src/inkstave/infra/mailer/sender.py` | `EmailSender` protocol, four backends, `get_email_sender` |
| `backend/src/inkstave/infra/mailer/enqueuer.py` | `EmailEnqueuer` |
| `backend/src/inkstave/infra/mailer/jobs.py` | `send_email_job` |
| `backend/src/inkstave/infra/deps.py` | `get_email_enqueuer` dependency |
| `backend/src/inkstave/worker.py` | Registers both jobs and the cron |
| `backend/src/inkstave/cli.py` | `send-test-email` |
| `frontend/src/modules/notifications` | `NotificationsBell`, polling hooks, API client |
| `frontend/src/i18n/locales/pt/notifications.ts` | Portuguese bell strings |
| `backend/tests/integration/test_notifications_service.py` | Service rules |
| `backend/tests/integration/test_notifications_api.py` | Routes |
| `backend/tests/integration/test_invite_notification_hook.py` | Invite hook |
| `backend/tests/integration/test_email_triggers_103.py` | Enqueue triggers in the auth routes |
| `backend/tests/unit/test_email_job.py` | The job |
| `backend/tests/unit/test_email_sender.py` | Factory, file and console senders, templates |
| `backend/tests/unit/test_resend_sender.py` | Resend sender, `send-test-email`, the config guard |

## Data

`notifications`, created by `backend/migrations/versions/20260610_1300_e5f7b9c13d46_create_notifications.py`.

| Column | Notes |
|---|---|
| `id` | UUID primary key |
| `user_id` | FK to `users`, `ON DELETE CASCADE` |
| `type` | Free `Text`. `NotificationType` lists `project_invite` and `generic`; there is no check constraint |
| `payload` | JSONB, default `{}` |
| `read_at`, `dismissed_at`, `expires_at` | Nullable timestamps |
| `created_at` | Set by the server; moved forward when a deduped row is refreshed |

Indexes: `ix_notifications_user_active` on `(user_id, created_at DESC)` where `dismissed_at IS NULL`, and
`ix_notifications_expiry` on `expires_at` where it is not null.

A `project_invite` payload holds `project_id`, `project_name`, `inviter_name`, `role`, `invite_id` and
`accept_url`. The only production writer is `notify_invite`. No code creates `generic` rows; the bell
renders them from `payload.message`.

E-mail has no table. A queued job lives in Redis. The `file` backend writes one JSON file per message
to `EMAIL_FILE_DIR`.

## Routes

All require a bearer token and act on the caller's own rows. Errors use the JSON envelope; the table lists
`error.type`.

| Method and path | What it does | Errors |
|---|---|---|
| `GET /api/v1/notifications` | Active rows, newest first, plus `unread_count`. Query `before`, `limit` (default 50, 1 to 100) | 422 `validation_error` |
| `GET /api/v1/notifications/unread-count` | `{count}` | |
| `POST /api/v1/notifications/{notification_id}/read` | Mark read, idempotent | 404 `notification_not_found` |
| `POST /api/v1/notifications/read-all` | Mark all active rows read, returns `{updated}` | |
| `DELETE /api/v1/notifications/{notification_id}` | Dismiss, 204, idempotent | 404 `notification_not_found` |

## How it works

### Inbox

Active means not dismissed and not past `expires_at`. `list_active`, `unread_count` and `mark_all_read`
share the `_active` predicate, so an expired row disappears before the sweep removes it.

`mark_read` and `dismiss` load through `get_owned` from `backend/src/inkstave/core/db/ownership.py`. A
missing id and another user's id raise the same 404. Dismiss is soft and keeps the row.

`create` takes an optional `dedupe_on=(key, value)`. If a non-dismissed row of the same user and type has
that payload value, the row is updated: new payload and expiry, `read_at` cleared, `created_at` set to now.
It therefore returns to the top as unread.

### Invite hook

`create_invite` in `backend/src/inkstave/modules/projects/routes/sharing.py` calls `notify_invite` after
the service call, inside the request's unit of work:

1. Builds `accept_url` from `FRONTEND_URL` as the SPA route `/invite/{raw_token}`.
2. If a user has the invited address, ignoring case, creates a `project_invite` row with expiry
   `NOTIFICATION_INVITE_TTL_DAYS` from now, deduped on `invite_id`.
3. Always enqueues the `project_invite` e-mail.

A person without an account gets only the e-mail. Registering later does not create a row.

### Expiry sweep

`sweep_notifications` calls `sweep_expired`, which hard-deletes rows with `expires_at <= now`, and commits.
It is safe to re-run. It returns `{"status": "swept", "removed": n}`. `WorkerSettings` registers it with
`max_tries=2` and a cron at minute 0 of each hour. Rows without `expires_at` are never deleted, even when
dismissed.

### E-mail pipeline

Handlers never send inline.

1. A route gets `EmailEnqueuer` from `get_email_enqueuer`. It shares the app's ARQ pool, or creates one.
2. `enqueue_email(template, to, context)` enqueues `send_email_job` on the queue named by
   `COMPILE_QUEUE_NAME`. All jobs share that queue and worker.
3. `send_email_job` renders with `render_email`, takes `ctx["email_sender"]` or `get_email_sender(settings)`,
   and sends an `OutgoingEmail`. It logs and re-raises on a send error. It returns
   `{"status": "sent", "template", "to"}` on success.

| Template | Sent by | Context | Subject |
|---|---|---|---|
| `project_invite` | `notify_invite` | `project_name`, `inviter_name`, `role`, `accept_url` | `{inviter} invited you to {project} on Inkstave` |
| `password_reset` | forgot password | `user_name`, `reset_url` | `Reset your Inkstave password` |
| `email_change_confirmation` | e-mail change | `user_name`, `confirm_url` | `Confirm your new Inkstave email` |
| `email_verification` | register, resend | `user_name`, `verify_url` | `Verify your Inkstave email` |
| `magic_login` | magic link | `user_name`, `magic_url` | `Your Inkstave sign-in link` |

Each template returns `(subject, text_body, html_body)`. They are plain Python functions in `_TEMPLATES`,
with no template engine. The HTML body escapes interpolated values with `html.escape`. An unknown name
raises `UnknownTemplateError`.

### Backends

`get_email_sender` picks one from `EMAIL_BACKEND`.

| Backend | Class | Behaviour |
|---|---|---|
| `resend` | `ResendEmailSender` | Posts to `/emails` with httpx, 10 s timeout, default base `https://api.resend.com`. Logs and raises on a transport error or status 400 and above. Never logs the key. An httpx transport can be injected for tests |
| `smtp` | `SmtpEmailSender` | `aiosmtplib.send` with `start_tls=SMTP_USE_TLS`, timeout `SMTP_TIMEOUT_S`. Empty user or password means no login. Raises on failure |
| `file` | `FileEmailSender` | One JSON file per message, written through `asyncio.to_thread` |
| `console` | `ConsoleEmailSender` | Logs the message at INFO on `inkstave.mailer`. Sends nothing |

### `send-test-email`

`python -m inkstave.cli send-test-email --to you@example.com` renders one template with placeholder
values from `_test_email_context` and sends it through the configured backend. `--template` picks the
template; the default is `email_verification`. It needs no worker or queue. It prints
`send-test-email: PASS` and returns 0, or prints `FAIL` to stderr and returns 1 on an unknown template or
any exception.

## Rules and guarantees

| Invariant | Test |
|---|---|
| Dismissed rows leave the list | `backend/tests/integration/test_notifications_service.py::test_dismiss_excludes_from_list` |
| Expired rows are hidden, then swept; the sweep is idempotent | `backend/tests/integration/test_notifications_service.py::test_expired_excluded_and_swept` |
| Another user's row is 404 in the service and over HTTP | `backend/tests/integration/test_notifications_service.py::test_ownership_enforced`, `backend/tests/integration/test_notifications_api.py::test_cross_user_404` |
| Mark read and mark all update the count | `backend/tests/integration/test_notifications_service.py::test_mark_read_and_mark_all` |
| A re-issued invite keeps one row and resurfaces it | `backend/tests/integration/test_notifications_service.py::test_dedupe_invite_notifications`, `backend/tests/integration/test_notifications_service.py::test_dedupe_refresh_resurfaces_notification` |
| An invite to an account creates a row and an e-mail | `backend/tests/integration/test_invite_notification_hook.py::test_invite_existing_user_creates_notification_and_email` |
| An invite to an unknown address sends only the e-mail | `backend/tests/integration/test_invite_notification_hook.py::test_invite_unknown_user_email_only` |
| The job renders and sends through the injected sender | `backend/tests/unit/test_email_job.py::test_job_renders_and_sends_via_injected_sender` |
| The job re-raises a send failure | `backend/tests/unit/test_email_job.py::test_job_reraises_on_send_failure`; asserts the raise, not a retry |
| User values are escaped in HTML | `backend/tests/unit/test_email_sender.py::test_project_invite_html_is_escaped` |
| An unknown template raises | `backend/tests/unit/test_email_sender.py::test_unknown_template_raises` |
| The factory selects each backend | `backend/tests/unit/test_email_sender.py::test_factory_selects_backend`, `backend/tests/unit/test_resend_sender.py::test_factory_selects_resend_and_keeps_others` |
| Resend errors raise and never expose the key | `backend/tests/unit/test_resend_sender.py::test_resend_raises_on_non_2xx_and_hides_key` |
| Forgot password does not reveal whether an account exists | `backend/tests/integration/test_email_triggers_103.py::test_forgot_password_same_response_known_or_unknown` |
| `send-test-email` passes and fails with the right exit code | `backend/tests/unit/test_resend_sender.py::test_cli_send_test_email_pass`, `backend/tests/unit/test_resend_sender.py::test_cli_send_test_email_fail_nonzero` |
| A missing Resend key is reported | `backend/tests/unit/test_resend_sender.py::test_validator_flags_missing_resend_key` |
| SMTP sending | no dedicated test |

## Settings

Defined in `backend/src/inkstave/core/config/groups.py`.

| Variable | Default | Effect |
|---|---|---|
| `EMAIL_BACKEND` | `console` | `smtp`, `console`, `file` or `resend` |
| `EMAIL_FROM` | `Inkstave <no-reply@inkstave.local>` | Default From header |
| `EMAIL_FILE_DIR` | `./tmp/emails` | Output of the `file` backend |
| `SMTP_HOST` | `localhost` | `check-config` requires it when the backend is `smtp` |
| `SMTP_PORT` | `587` | |
| `SMTP_USER`, `SMTP_PASSWORD` | empty | Empty means no login |
| `SMTP_USE_TLS` | `true` | STARTTLS |
| `SMTP_TIMEOUT_S` | `30.0` | Per operation, must be above 0 |
| `RESEND_API_KEY` | empty | Needed by the `resend` backend. A production boot fails without it, and `check-config` reports it |
| `FRONTEND_URL` | `http://localhost:5173` | Base of every link in e-mail |
| `APP_BASE_URL` | `http://localhost` | Used only by the `send-test-email` placeholders |
| `NOTIFICATION_INVITE_TTL_DAYS` | `30` | Lifetime of an invite notification |
| `NOTIFICATION_SWEEP_INTERVAL_S` | `3600` | Read by nothing; see below |
| `VITE_NOTIFICATIONS_POLL_INTERVAL_MS` | `60000` | Frontend poll of the unread count |

## Points of attention

- **Failed e-mails are not retried.** `send_email_job` has `max_tries=3`, and its docstring says a re-raise
  lets ARQ retry. ARQ retries only `Retry`, `RetryJob` and cancellation. Any other exception marks the job
  failed on the first try. A transient SMTP or Resend failure therefore loses the e-mail and leaves only
  a log line.
- **E-mail is English only.** All subjects and bodies are hard-coded English in
  `backend/src/inkstave/infra/mailer/templates.py`, and `render_email` has no language parameter. The
  invite body inserts the raw role word `editor` or `viewer`.
- **No source for the language exists yet.** No backend file reads a locale or `Accept-Language`, and
  the user has no stored preference. The frontend detects the language in the browser and keeps it there.
  A localized e-mail needs a language value carried in the `context` of `enqueue_email`, and a source for
  it: a new user preference for account e-mails. An invite to a non-user has no recipient record, so it
  would need another choice, such as the inviter's language.
- **Bell strings are localized, the payload is not.** `NotificationsBell` translates the sentence but
  inserts `payload.role` as stored, so Portuguese text carries the English role word.
- **`message` strings are English.** `Notification not found.` is the only one in the inbox. The API has no
  `detail` field and does not emit `application/problem+json`; see the sharing doc.
- **The raw invite token is stored.** `accept_url` in the notification payload contains the token as
  plain text in JSONB. The comment on `token_hash` in
  `backend/src/inkstave/modules/projects/models/invite.py` says it is never persisted.
- **Invite notifications go stale.** Accept, decline and revoke do not touch the row. It stays until
  dismissed or expired, with its Accept button, which then leads to the 410 screen. Its 30-day lifetime is
  also longer than the 14-day invite.
- **Enqueue runs before commit.** `notify_invite` enqueues inside the unit of work. If the commit then
  fails, an e-mail goes out with a dead token. If Redis is down, the enqueue error fails the request and the
  invite rolls back.
- **`NOTIFICATION_SWEEP_INTERVAL_S` has no effect.** The cron is fixed to hourly. A comment in
  `backend/src/inkstave/worker.py` says the setting only documents intent.
- **`APP_BASE_URL` is misdescribed.** `.env.example` calls it the base for e-mail URLs. All real links
  use `FRONTEND_URL`.
- **`send-test-email` gaps.** `_test_email_context` claims to cover every template's keys but has no
  `magic_url`, so `--template magic_login` reports `FAIL` with a `KeyError`. Its `accept_url` has the
  shape `/invite?token=`, not the real route. Sending the invite template is a transport test only.
- **Secrets in logs.** `ConsoleEmailSender`, the default backend, logs the full text body at INFO, which
  includes tokens in links. `check-config` does not flag `console` in production, so a deployment that
  keeps the default sends nothing and logs live links. `send_email_job` and the Resend sender also log the
  recipient address.
- **SMTP port 465.** `.env.example` offers 465 for Resend, but `SmtpEmailSender` passes only `start_tls`
  and never enables implicit TLS, which that port expects.
- **Dedupe has no unique index.** It is a read-then-write, so two concurrent `create` calls can both
  insert.
