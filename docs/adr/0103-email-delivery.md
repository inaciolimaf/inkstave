# ADR 0103 — Email delivery (Mailpit dev inbox + Resend production)

**Status:** accepted (spec 103) · **Phase:** 7 — Hardening, packaging & docs

## Context

Spec 39 built the async email pipeline (`EmailSender` Protocol,
SMTP/console/file senders, `get_email_sender` DI, `send_email_job`,
`EmailEnqueuer`, `render_email`). Spec 103 makes it usable end-to-end: a local
**Mailpit** inbox with zero provider account, a documented free **Resend**
production path (over SMTP *or* a native HTTP-API sender), and the two missing
transactional triggers — without new database tables.

## Transactional templates — what was already wired vs filled here

| Template | Before spec 103 | Spec 103 |
| --- | --- | --- |
| `project_invite` | enqueued in `notifications/invite_hook.py` (spec 33) | **unchanged** |
| `email_change_confirmation` | enqueued in `users.py::change_email` (spec 59) | **unchanged** |
| `password_reset` | template existed, **no trigger** | **added** `POST /api/v1/auth/forgot-password` (non-enumerating) that enqueues it |
| `email_verification` | **no template, no trigger** | **added** template + enqueue on `POST /api/v1/auth/register` |

No working flow was rewritten.

## Resend: two paths, one DI seam

`EMAIL_BACKEND=smtp` with `SMTP_HOST=smtp.resend.com` reuses the existing
`SmtpEmailSender` (zero new code). `EMAIL_BACKEND=resend` selects a new native
`ResendEmailSender` (httpx POST to `api.resend.com/emails`) through the existing
`get_email_sender` factory. It opens no connection at construction, never logs the
API key, raises on any non-2xx / transport error (so `send_email_job` retries),
and logs the Resend message id at DEBUG on success. `check-config`/`doctor` flag
an empty `RESEND_API_KEY` when `EMAIL_BACKEND=resend` (and a missing `SMTP_HOST`
when `EMAIL_BACKEND=smtp`).

## Tokens for reset/verification: stateless emission, no new table

The spec forbids new tables and the `User` model has no reset/verification
columns. The **consuming** endpoints (reset-password, verify-email completion +
their pages) are explicitly out of scope (deferred to a future auth-UI spec), so
this spec emits an opaque `generate_token()` value inside the link
(`{frontend_url}/reset-password?token=…`, `{frontend_url}/verify-email?token=…`)
and persists **nothing** — no table, no column, no migration. The deliverable is
the transport + triggers + correct links; token persistence/verification arrives
with the completion endpoints. This is called out here per spec §5.1.

The new TTL settings (`password_reset_token_ttl`, `email_verification_token_ttl`)
are added for when those completion endpoints land.

## Mailpit is dev-only

`mailpit` (`axllent/mailpit`) is added to `docker-compose.dev.yml` only (SMTP on
1025, UI on 8025) and **never** to `docker-compose.prod.yml`. The dev
backend/worker reach it via `host.docker.internal` + the published `1025` port —
consistent with this host's DB/Redis DNS-avoidance (embedded Docker DNS is flaky
here); on a healthy-DNS host `SMTP_HOST=mailpit` also works. A `just mail` recipe
opens the inbox; a `send-test-email` CLI verifies transport without a worker.

## Tests stay hermetic

No automated test touches Mailpit, a real SMTP server, or Resend: the
`ResendEmailSender` is exercised against an `httpx.MockTransport`, the enqueuer is
a capturing fake, and the CLI test injects a fake sender. The suite stays under
the 2-minute budget.

## Originality

Overleaf's Email feature (`EmailBuilder`/`EmailSender`/`EmailHandler`) was read
for structure only (AGPLv3 vs MIT). Overleaf has **no** Mailpit dev service and
**no** Resend integration — those, plus `ResendEmailSender` and the
`send-test-email` CLI, are written from scratch.
