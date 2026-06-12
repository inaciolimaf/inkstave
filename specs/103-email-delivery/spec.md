# Spec 103 — Email delivery (Mailpit dev inbox + Resend production) (requirements)

## 1. Summary

Spec 39 already built a pluggable, async email pipeline (the `EmailSender`
Protocol, `ConsoleEmailSender`/`FileEmailSender`/`SmtpEmailSender`,
`get_email_sender` DI, the `send_email_job` ARQ job, `EmailEnqueuer`, and
`render_email` templates). This spec makes that pipeline **genuinely usable
end-to-end**: locally a developer captures and *sees* every outgoing email in a
**Mailpit** inbox (`http://localhost:8025`) with zero provider account; in
production the system delivers real mail through **Resend** (recommended free
provider, ~3k emails/month) either over the *existing* `SmtpEmailSender` (config
only, zero new code) or through an *optional* native HTTP-API sender
`ResendEmailSender`. It also closes the remaining transactional-email gaps
(account email verification and password reset have templates but no trigger /
no template yet) and adds a manual `send-test-email` CLI plus a `just mail`
recipe so the wiring can be verified by hand. The Protocol/DI boundary is kept
intact so the fast test suite swaps a fake and never touches a real SMTP server,
Mailpit, or Resend.

## 2. Context & dependencies

- **Depends on:**
  - **Spec 39** — the mailer package (`backend/src/inkstave/mailer/`): `EmailSender`
    Protocol + `OutgoingEmail` dataclass (`sender.py`), `get_email_sender(settings)`
    factory, `SmtpEmailSender`/`ConsoleEmailSender`/`FileEmailSender`,
    `send_email_job` (`jobs.py`, registered in `compile/worker.py` with
    `max_tries=3`), `EmailEnqueuer` (`enqueuer.py`), `render_email` + the
    `_TEMPLATES` registry (`templates.py`).
  - **Specs 06–08** — `User` model, JWT auth, auth guards/sessions (the password
    reset + email-verification flows attach to these).
  - **Spec 59** — user settings / profile: `account.start_email_change`, the
    `change_email` route in `api/routes/users.py` (already enqueues
    `email_change_confirmation`), and `email_change_token_ttl` in
    `config_groups.py`.
  - **Spec 33** — sharing invites: `notifications/invite_hook.py` already enqueues
    the `project_invite` email.
- **Unlocks:** reliable transactional email in every environment; a documented
  free production email path; a manual end-to-end verification tool. No later
  spec is blocked on it, but observability/security specs benefit from the
  bounce/error logging defined here.
- **Affected areas:** backend (`mailer/`, `cli.py`, `config_groups.py`, the auth
  routes for password reset + verification, DI in `dependencies.py`), infra
  (`docker-compose.dev.yml`, `justfile`), config (`.env.example`), docs
  (admin/operations guide under `docs/`).

## 3. Goals

- **Local/dev:** add a **Mailpit** (`axllent/mailpit`) service to
  `docker-compose.dev.yml` exposing **SMTP on 1025** and a **web UI on 8025**;
  wire dev backend/worker env so `EMAIL_BACKEND=smtp`, `SMTP_HOST=mailpit`,
  `SMTP_PORT=1025`, no TLS, no auth — so the existing `SmtpEmailSender` delivers
  into Mailpit and the developer sees every email at `http://localhost:8025`.
- **Production:** support **Resend** two ways, both selectable by config:
  1. **SMTP path (zero new code):** `EMAIL_BACKEND=smtp`,
     `SMTP_HOST=smtp.resend.com`, `SMTP_PORT=587` (or `465`), `SMTP_USER=resend`,
     `SMTP_PASSWORD=<RESEND_API_KEY>`, `SMTP_USE_TLS=true` → existing
     `SmtpEmailSender` delivers. Documentation only.
  2. **Native HTTP-API path (optional):** a new `ResendEmailSender` implementing
     the `EmailSender` Protocol, posting to `https://api.resend.com/emails`,
     selected by `EMAIL_BACKEND=resend` through the existing `get_email_sender`
     DI. No business logic touches it directly.
- **Complete the transactional set:** ensure **account email verification**,
  **password reset**, **project invite**, and **email-change confirmation** all
  (a) go through the async `send_email_job` (never block a request) and (b) have
  proper subject + text + HTML templates. Project-invite and email-change are
  already wired (state so); fill the gaps for the other two.
- **Reliability:** keep the existing raise-for-retry behaviour (sender raises →
  job re-raises → ARQ retries with backoff); add bounce/error logging.
- **Operability:** a `just mail` recipe (open/serve the local inbox) and a manual
  `python -m inkstave.cli send-test-email` command to verify wiring end to end.
- **Tests stay fast & hermetic:** no automated test touches Mailpit, a real SMTP
  server, or Resend; the suite stays under 2 minutes.

## 4. Non-goals (explicitly out of scope)

- No marketing/bulk email, mailing lists, digests, or scheduling.
- No email-template theming system, MJML, or per-locale i18n (single English
  text+HTML per template, matching the existing `templates.py` style).
- No in-app inbox/notification-centre work (that is spec 39's notifications).
- No provider abstraction beyond Resend + generic SMTP (no SendGrid/SES/Postmark
  adapters). Resend over SMTP already covers "any SMTP provider".
- No DNS automation: SPF/DKIM/domain verification for Resend is **documentation
  only**, not code.
- No new database tables. Password-reset / verification token storage reuses the
  pattern already established for email-change tokens (spec 59); if spec 06–08
  already provide a verification/reset token mechanism, reuse it and do not add a
  table.

## 5. Detailed requirements

### 5.1 Data model (if any)

No new tables are introduced by the email transport itself.

Password-reset and email-verification tokens (needed to wire the two missing
triggers) **reuse the existing token mechanism**. The implementer MUST first
check what specs 06–08 and 59 already provide:

- If a reusable signed/opaque token utility exists (as used by
  `account.start_email_change` with `email_change_token_ttl`), reuse it with new
  purpose/TTL settings — no migration.
- Only if **no** reusable mechanism exists may a minimal token row be added, and
  then it ships an Alembic migration following the existing migration conventions
  (`backend/migrations/`, never edit a released migration). Prefer reuse; adding
  a table here is a last resort and must be called out in the ADR.

New config defaults for these flows (added to the relevant settings mixin in
`config_groups.py`):

- `password_reset_token_ttl: int = 3600` — password-reset link lifetime (seconds).
- `email_verification_token_ttl: int = 86400` — account-verification link lifetime.

### 5.2 Backend / API

#### 5.2.1 `ResendEmailSender` (new, optional native sender)

Add to `backend/src/inkstave/mailer/sender.py`, alongside the existing senders,
implementing the existing `EmailSender` Protocol:

```python
class ResendEmailSender:
    """Sends via the Resend HTTP API. Raises on failure so the ARQ job retries."""

    def __init__(
        self,
        *,
        api_key: str,
        default_from: str,
        base_url: str = "https://api.resend.com",
        timeout_s: float = 10.0,
    ) -> None: ...

    async def send(self, email: OutgoingEmail) -> None: ...
```

Contract for `send`:

- Builds the JSON payload Resend expects:
  - `from`: `email.from_addr or self._default_from`
  - `to`: `[email.to]` (Resend takes a list)
  - `subject`: `email.subject`
  - `text`: `email.text_body`
  - `html`: `email.html_body` only when not `None` (omit the key otherwise)
- POSTs to `{base_url}/emails` with header
  `Authorization: Bearer {api_key}` and `Content-Type: application/json`,
  using an `httpx.AsyncClient` (httpx is already a dependency, `httpx>=0.28`).
  Honour `timeout_s`.
- On a non-2xx response, **raise** (use `response.raise_for_status()` or an
  explicit raise) so `send_email_job` re-raises and ARQ retries. On a transport
  error (`httpx.HTTPError`/timeout) it must also propagate (raise), not swallow.
- On success (2xx) it returns `None`. It MUST NOT log the API key. It SHOULD log
  the Resend message id at DEBUG when present in the response body.
- It MUST NOT open any connection at construction time (so importing/constructing
  it in `get_email_sender` is cheap and safe in tests).

Extend `get_email_sender(settings)` with a `resend` branch (placed before the
fallthrough), keeping the existing `smtp`/`file`/`console` branches unchanged:

```python
if settings.email_backend == "resend":
    return ResendEmailSender(
        api_key=settings.resend_api_key,
        default_from=settings.email_from,
    )
```

Export `ResendEmailSender` from `mailer/__init__.py` `__all__`.

#### 5.2.2 Templates (extend `templates.py`)

`templates.py` already has `project_invite`, `password_reset`, and
`email_change_confirmation` renderers in `_TEMPLATES`. Add **one** new renderer
and register it; do not modify the existing three except as noted:

- `email_verification` — context: `{"user_name"?, "verify_url"}`. Subject e.g.
  `"Verify your Inkstave email"`. Text + HTML bodies in the existing style
  (greeting, one-line reason, the `verify_url` link, an "ignore this email"
  footer). HTML MUST `escape(...)` every interpolated value exactly as the
  existing renderers do (`escape(str(verify_url), quote=True)` inside `href`),
  per the spec-40 XSS rule.

All link-bearing templates MUST build their URLs from `APP_BASE_URL` /
`frontend_url` at the **call site** (the route/hook that enqueues), exactly as
`change_email` does today (`f"{settings.frontend_url}/settings/confirm-email?token=..."`).
Templates receive a ready-made absolute URL in their context; they do not know
about settings. (Document which base each link uses; reset/verify links built
from `app_base_url` or `frontend_url` consistently with the existing
email-change link.)

`render_email(template, context)` and `UnknownTemplateError` are unchanged.

#### 5.2.3 Wire the missing transactional triggers

Inventory (verify against the live code before implementing):

| Template | Trigger today | Action |
| --- | --- | --- |
| `project_invite` | enqueued in `notifications/invite_hook.py` (spec 33) | **already wired — leave as is**, just confirm it still enqueues exactly one job. |
| `email_change_confirmation` | enqueued in `api/routes/users.py::change_email` (spec 59) | **already wired — leave as is**. |
| `password_reset` | template exists; **no route enqueues it** | wire the forgot-password flow to enqueue it. |
| `email_verification` | **no template, no trigger** | add template (5.2.2) + wire the trigger. |

For each newly wired flow:

- The request handler MUST NOT send inline. It generates the token + absolute
  URL, then calls `EmailEnqueuer.enqueue_email(template=..., to=..., context=...)`
  (injected via the existing `get_email_enqueuer` DI in `dependencies.py`) so the
  ARQ `send_email_job` does the actual send. The HTTP response returns
  immediately (`202 Accepted` is the established pattern, see `change_email`).
- **Password reset:** a public `POST /api/auth/forgot-password` (or the
  established auth-route path) accepting `{ "email": <EmailStr> }`. It MUST be
  **non-enumerating**: always return the same `202`/`MessageResponse` whether or
  not the address exists; only enqueue the email when a matching active user is
  found. Reuse the auth/token utilities from specs 06–08; build
  `reset_url = f"{settings.frontend_url}/reset-password?token={raw_token}"`
  (match the existing email-change URL convention). Rate-limit it with the
  existing rate-limit machinery if trivially available; if the existing
  forgot-password route already exists, only add the missing `enqueue_email`
  call.
- **Email verification:** trigger on registration (and/or a "resend verification"
  endpoint if one already exists). On user creation, enqueue `email_verification`
  to the new address with
  `verify_url = f"{settings.frontend_url}/verify-email?token={raw_token}"`. Do not
  block registration on the send. If specs 06–08 already deliberately omit
  verification, the implementer adds the minimal trigger described here and notes
  it in the ADR; keep it behind the existing flow so tests that register users
  still pass (the enqueue is a fire-and-forget side effect through the fake
  enqueuer in tests).

> The implementer MUST state, in the PR/ADR, exactly which of the four templates
> were already wired and which gaps this spec filled — do not silently
> re-implement working flows.

#### 5.2.4 Retry / failure / bounce-logging policy

- `send_email_job` already wraps `sender.send(...)` in try/except, logs
  `email_send_failed` at exception level, and re-raises so ARQ retries. Keep this.
  `SmtpEmailSender` and the new `ResendEmailSender` both **raise** on failure so
  this works for every production backend.
- Confirm `send_email_job` is registered with a bounded retry policy in
  `compile/worker.py` (currently `max_tries=3`). Document the effective backoff
  (ARQ's default exponential backoff between tries). Do not add unbounded retries.
- **Bounce/error logging:** on a failed send the log line MUST include the
  template name and recipient (already present) and, for Resend, the HTTP status
  and any error code/message from the response body — **never** the API key. A
  synchronous (4xx, e.g. invalid recipient) failure that is not worth retrying
  MAY be distinguished in the log message, but the simplest acceptable behaviour
  is: raise on any non-2xx, let ARQ exhaust `max_tries`, and log each failure.
  Re-sending on retry is acceptable (idempotency is not required), matching the
  spec-39 note in `jobs.py`.

#### 5.2.5 `send-test-email` CLI subcommand

Extend `backend/src/inkstave/cli.py` (stdlib `argparse`, matching the existing
`migrate`/`doctor`/`seed` commands) with:

```
python -m inkstave.cli send-test-email --to you@example.com [--template email_verification]
```

Behaviour:

- Loads `get_settings()`, builds the sender via `get_email_sender(settings)`
  (so it uses whatever `EMAIL_BACKEND` is configured — Mailpit in dev, Resend in
  prod), renders the chosen template (default a simple built-in test message or
  `email_verification` with placeholder context), and calls `sender.send(...)`
  **directly** (this command is the one place that sends synchronously, on
  purpose, so the developer can verify transport without a running worker).
- Prints a one-line PASS/`sent to <addr> via <backend>` on success and a clear
  non-zero-exit FAIL line on error (no traceback), like the existing `doctor`
  probes.
- Registered in `main()` with its own subparser; returns a process exit code.
- This command is **manual-only**: it is exercised by a unit test against a fake
  sender (no network), never against real SMTP/Mailpit/Resend in the fast suite.

### 5.3 Frontend / UI

No new UI is required by this spec. (Reset-password / verify-email pages belong
to the auth/settings UI specs; this spec only guarantees the emails carry correct
links built from `frontend_url`/`app_base_url`.) If the implementer adds a
trigger that needs a landing route that does not yet exist, it is sufficient to
emit the link the existing frontend already handles; do not build new pages here.

### 5.4 Real-time / jobs / external integrations

- **ARQ job:** unchanged signature
  `send_email_job(ctx, *, template, to, context)`; every transactional email goes
  through it via `EmailEnqueuer.enqueue_email`. No request handler calls
  `sender.send` (except the manual CLI in 5.2.5).
- **External integration — Resend HTTP API:** `ResendEmailSender` is the only
  code that talks to `api.resend.com`. It uses `httpx.AsyncClient`. In tests it is
  exercised against a **mocked httpx transport** (`httpx.MockTransport` / a custom
  `ASGITransport`-free handler) — no network, no key.
- **External integration — Mailpit:** dev only, via SMTP through the existing
  `SmtpEmailSender`. Not referenced by any code; purely an SMTP target supplied
  by dev compose env.

### 5.5 Configuration

#### 5.5.1 New / changed settings (`config_groups.py`)

- Widen `email_backend` literal:
  `email_backend: Literal["smtp", "console", "file", "resend"] = "console"`.
- Add `resend_api_key: str = ""` (secret; sourced from env, never defaulted to a
  real value). It is required **only** when `email_backend == "resend"` — the
  config validator (`bootstrap/config_check.py`) MUST flag an empty
  `resend_api_key` when `EMAIL_BACKEND=resend`, the same way other backend-gated
  secrets are validated. Similarly, when `EMAIL_BACKEND=smtp` the validator
  should already (or now) sanity-check that `SMTP_HOST` is set.
- Add `password_reset_token_ttl: int = 3600` and
  `email_verification_token_ttl: int = 86400` (per 5.1).
- The new `ResendEmailSender` reads `resend_api_key`, `email_from`, and (with
  defaults) base URL / timeout; no other new settings are required for transport.

#### 5.5.2 `.env.example`

Update the email block. Final intended state of the relevant section:

```dotenv
# --- Email + notifications (spec 39 / 102) ---
EMAIL_BACKEND=console                     # smtp | console | file | resend  (console in dev/tests)
EMAIL_FROM=Inkstave <no-reply@inkstave.local>  # default From header
EMAIL_FILE_DIR=./tmp/emails               # output dir for the FileEmailSender
SMTP_HOST=localhost                       # SMTP host (dev via Mailpit: mailpit; Resend: smtp.resend.com)
SMTP_PORT=587                             # SMTP port (Mailpit: 1025; Resend: 587 or 465)
SMTP_USER=                                # SMTP username (Mailpit: empty; Resend: resend)
SMTP_PASSWORD=                            # SMTP password (Resend: your RESEND_API_KEY)
SMTP_USE_TLS=true                         # STARTTLS/TLS (Mailpit: false; Resend: true)
APP_BASE_URL=http://localhost             # base for accept_url / reset_url / verify_url in emails

# Native Resend HTTP API sender (optional; only used when EMAIL_BACKEND=resend).
# Get a key at https://resend.com (free tier ~3k emails/month). NEVER commit a real key.
RESEND_API_KEY=                           # Resend API key (re_...) — required iff EMAIL_BACKEND=resend

# Token lifetimes for transactional links (spec 103).
PASSWORD_RESET_TOKEN_TTL=3600             # password-reset link lifetime (seconds)
EMAIL_VERIFICATION_TOKEN_TTL=86400        # account email-verification link lifetime
```

A short comment block in `.env.example` MUST document the three concrete recipes
(dev/Mailpit, Resend-over-SMTP, Resend-native) so a reader can flip between them.

#### 5.5.3 Dev compose — Mailpit service (`docker-compose.dev.yml`)

Add a `mailpit` service and point the backend/worker dev env at it. The shared
`x-backend-env` anchor gains the SMTP/email keys (so both `backend` and `worker`
inherit them):

```yaml
x-backend-env: &backend-env
  ENVIRONMENT: dev
  # ...existing keys...
  # Email → Mailpit (captured locally, viewable at http://localhost:8025)
  EMAIL_BACKEND: smtp
  SMTP_HOST: mailpit
  SMTP_PORT: "1025"
  SMTP_USER: ""
  SMTP_PASSWORD: ""
  SMTP_USE_TLS: "false"

services:
  # ...postgres, redis, backend, worker, frontend...

  mailpit:
    image: axllent/mailpit:latest
    restart: unless-stopped
    ports:
      - "8025:8025"   # web UI  → http://localhost:8025
      - "1025:1025"   # SMTP    → senders deliver here
    environment:
      MP_SMTP_AUTH_ACCEPT_ANY: "true"
      MP_SMTP_AUTH_ALLOW_INSECURE: "true"
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost:8025/readyz"]
      interval: 5s
      timeout: 3s
      retries: 10
```

`backend` and `worker` add `mailpit` to their `depends_on` (the worker is what
actually runs `send_email_job`, so it must reach Mailpit). Because the dev env
reaches other services via `host.docker.internal` for DNS reasons (see the
compose header comment), `SMTP_HOST: mailpit` relies on Docker's embedded DNS for
this one extra name; if that proves flaky on the target host, document the
fallback of `SMTP_HOST: host.docker.internal` + the published `1025` port (Mailpit
already publishes it). Mailpit is **dev only** — it must NOT appear in
`docker-compose.prod.yml`.

#### 5.5.4 `justfile`

Add a recipe:

```make
# Open the local Mailpit inbox (dev). Mailpit must be up (docker compose -f docker-compose.dev.yml up).
mail:
    @echo "Mailpit inbox: http://localhost:8025"
    -xdg-open http://localhost:8025 >/dev/null 2>&1 || true
```

(Keep it tolerant on headless machines — print the URL and best-effort open.)

#### 5.5.5 Docs (admin / operations guide under `docs/`)

Add or extend an admin/operations doc covering:

1. **Local dev:** run `docker compose -f docker-compose.dev.yml up`, send any
   email (register, invite, reset, change-email), open `http://localhost:8025`
   (or `just mail`) and see it. Note tests do NOT need Mailpit.
2. **Production with Resend (SMTP path):** the exact env (`EMAIL_BACKEND=smtp`,
   `SMTP_HOST=smtp.resend.com`, `SMTP_PORT=587`/`465`, `SMTP_USER=resend`,
   `SMTP_PASSWORD=<RESEND_API_KEY>`, `SMTP_USE_TLS=true`) — zero code change.
3. **Production with Resend (native API path):** `EMAIL_BACKEND=resend` +
   `RESEND_API_KEY=...`.
4. **SPF / DKIM / domain verification (Resend):** add the domain in the Resend
   dashboard, create the published DNS records (SPF `TXT`, DKIM `CNAME`/`TXT`,
   and the recommended DMARC `TXT`), wait for verification, then set `EMAIL_FROM`
   to an address on the verified domain. Explain *why* (deliverability / not
   landing in spam) — **documentation only, no code**.
5. **Verifying end to end:** `python -m inkstave.cli send-test-email --to you@…`.
6. **Secrets:** `RESEND_API_KEY` and SMTP password come from env/secret store;
   never commit them; `.env` is git-ignored and `.env.example` carries empty
   placeholders.

## 6. Overleaf reference (study only — never copy)

Verified present in `../overleaf/`:

- `services/web/app/src/Features/Email/EmailBuilder.mjs` — how Overleaf assembles a
  transactional email (subject + text + HTML from a template/context). Learn the
  *structure*; Inkstave keeps its own `render_email` registry.
- `services/web/app/src/Features/Email/EmailSender.mjs` — how Overleaf abstracts the
  actual send (transport + error handling). Learn the *seam*; Inkstave already has
  its own `EmailSender` Protocol + `get_email_sender` DI — reuse that, do not
  mirror Overleaf's class.
- `services/web/app/src/Features/Email/EmailHandler.mjs` — how triggers hand off to
  the sender. Learn the *enqueue-then-send* split; Inkstave uses ARQ
  (`EmailEnqueuer` → `send_email_job`).
- `services/web/app/src/Features/Email/Bodies/`, `Layouts/`, `emailStyles.mjs`,
  `SpamSafe.mjs` — body/layout/spam-safety ideas (e.g. escaping user content).
  Inkstave already escapes in `templates.py`; treat as a checklist only.

**No Overleaf equivalents** (state explicitly): Overleaf has **no Mailpit dev
service and no Resend integration** — those parts of this spec are Inkstave-
specific and have nothing to reference. The native `ResendEmailSender` and the
`send-test-email` CLI are written from scratch.

## 7. Acceptance criteria

1. **Given** `EMAIL_BACKEND=resend` and a non-empty `RESEND_API_KEY`, **when**
   `get_email_sender(settings)` is called, **then** it returns a
   `ResendEmailSender`; existing `smtp`/`file`/`console` selections are unchanged.
2. **Given** a `ResendEmailSender` wired to a **mocked** httpx transport, **when**
   `send(OutgoingEmail(...))` is called, **then** exactly one `POST` is made to
   `https://api.resend.com/emails` carrying header
   `Authorization: Bearer <api_key>`, JSON body with `from`, `to: [addr]`,
   `subject`, `text`, and `html` (only when an HTML body was supplied), and the
   API key appears in **no** log output.
3. **Given** the mocked transport returns a non-2xx (e.g. 422) or raises a
   transport error, **when** `send(...)` runs, **then** it **raises** (so
   `send_email_job` re-raises and ARQ retries) and the failure is logged with the
   template/recipient and HTTP status but **not** the key.
4. **Given** any transactional trigger (project invite, email-change confirmation,
   password reset, email verification), **when** the trigger fires, **then**
   exactly **one** `send_email_job` is enqueued with the correct `template` name
   and recipient, the HTTP request returns immediately (no inline send), and a
   captured fake enqueuer records it.
5. **Given** the `password_reset` flow, **when** `POST /api/auth/forgot-password`
   is called for an **unknown** email, **then** the response is the same
   `202`/success as for a known email (no user enumeration) and **no** job is
   enqueued; for a **known** active user, exactly one `password_reset` job is
   enqueued with a `reset_url` built from `frontend_url`.
6. **Given** any link-bearing template is rendered, **when** the text and HTML
   bodies are produced, **then** both contain the absolute URL passed in context
   (built from `APP_BASE_URL`/`frontend_url`), all interpolated values are HTML-
   escaped in the HTML body, and `render_email("email_verification", …)` returns a
   subject + non-empty text + non-empty HTML.
7. **Given** the dev stack (`docker-compose.dev.yml`), **when** the developer
   triggers any email and opens `http://localhost:8025`, **then** the email is
   visible in Mailpit (manual acceptance — the dev env sets `EMAIL_BACKEND=smtp`,
   `SMTP_HOST=mailpit`, `SMTP_PORT=1025`, no TLS/auth, and `mailpit` exposes
   `8025`/`1025`). Mailpit appears only in the **dev** compose file.
8. **Given** `python -m inkstave.cli send-test-email --to a@b.com`, **when** run
   with a fake sender (test) or against the configured backend (manual), **then**
   it renders + sends a single test email and prints a PASS line; on transport
   error it prints a FAIL line and exits non-zero.
9. **Given** the config validator, **when** `EMAIL_BACKEND=resend` and
   `RESEND_API_KEY` is empty, **then** `check-config`/`doctor` reports the missing
   key and exits non-zero.
10. **Given** the full automated test suite, **when** it runs, **then** it
    completes in **< 2 minutes** and makes **no** connection to a real SMTP
    server, Mailpit, or Resend.

## 8. Test plan

> All tests combined across the project must keep the suite under 2 minutes.
> Slow/network work (real SMTP, Mailpit, Resend) is excluded from the fast suite.

- **Unit (pytest), extend `backend/tests/unit/test_email_sender.py` + new file
  `test_resend_sender.py`:**
  - `get_email_sender` returns `ResendEmailSender` for `email_backend="resend"`
    and still returns the right type for `smtp`/`file`/`console` (extends the
    existing `test_factory_selects_backend`).
  - `ResendEmailSender.send` against an `httpx.MockTransport`: asserts URL,
    `Authorization: Bearer <key>` header, JSON shape (`to` is a list; `html`
    omitted when `None`, present when supplied); success path returns `None`.
  - `ResendEmailSender.send` on a 422 response and on a simulated transport error
    both **raise**; assert (via `caplog`) the log line excludes the API key.
  - `render_email("email_verification", {...})` returns subject + text + html;
    link present in both bodies; HTML escapes interpolated values (mirror the
    existing `test_project_invite_template`).
  - CLI: `send-test-email` with an injected fake sender sends exactly one email
    and returns exit code 0; on a raising fake sender it returns non-zero and
    prints a FAIL line (no traceback).
  - Config validator flags empty `RESEND_API_KEY` when `EMAIL_BACKEND=resend`.
- **Integration (pytest + httpx ASGI + fake Redis/enqueuer):**
  - `POST /api/auth/forgot-password`: unknown email → 202 and **zero** jobs
    captured; known user → 202 and exactly one `password_reset` job with the
    right `to` and a `reset_url`. (Non-enumeration assertion.)
  - Registration (or resend-verification endpoint) enqueues exactly one
    `email_verification` job to the new address, and the response is unaffected by
    the email side effect (fake enqueuer that records jobs).
  - Confirm the existing `change_email` (spec 59) and invite (spec 33) flows still
    enqueue exactly one job each (regression guard; reuse existing fixtures —
    `test_account_api_59.py`, `test_invite_notification_hook.py`).
- **E2E (Playwright):** none required at this stage (no new UI). The Mailpit visual
  check (criterion 7) is a documented **manual** step, not an automated test.
- **Performance/budget note:** every sender test uses an in-memory fake or
  `httpx.MockTransport`; the enqueuer is the capturing fake; no test starts
  Mailpit, opens an SMTP socket, or calls Resend. The manual `send-test-email` and
  the Mailpit visual check are explicitly out of the automated suite.

## 9. Definition of Done

- [ ] All requirements in §5 implemented (Resend native sender + `get_email_sender`
      branch; Mailpit dev service + dev email env; `RESEND_API_KEY` /
      `EMAIL_BACKEND=resend` config + validator; `email_verification` template;
      password-reset + verification triggers wired through ARQ; `send-test-email`
      CLI; `just mail`; admin-guide docs).
- [ ] The PR/ADR states **which** of the four transactional templates were already
      wired (project invite, email-change) and which gaps were filled
      (password reset, email verification). No working flow rewritten.
- [ ] All acceptance criteria in §7 pass.
- [ ] All tests in §8 written and green.
- [ ] **Full suite runs in < 2 minutes.**
- [ ] **No real external email in automated tests** — no Mailpit, no real SMTP,
      no Resend network call or key in the fast suite (httpx mocked, sender faked).
- [ ] Lint/format/type-check clean (`ruff`, `mypy`).
- [ ] New env vars documented in `.env.example`; `docs/` updated with the dev
      Mailpit recipe, the two Resend production paths, and SPF/DKIM/domain notes.
- [ ] Secrets are env-sourced; `RESEND_API_KEY`/SMTP password never hard-coded or
      logged.
- [ ] Mailpit is in `docker-compose.dev.yml` only, **not** in the prod compose.
- [ ] **No Overleaf code copied** (Email feature studied for structure only).
