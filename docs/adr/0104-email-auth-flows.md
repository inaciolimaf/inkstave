# ADR 0104 — Email link-based account flows (verify / magic-link / reset)

**Status:** accepted (spec 104) · **Phase:** 7 — Hardening, packaging & docs

## Context

Specs 39 + 103 built the email *delivery* pipeline and two transactional
templates (`email_verification`, `password_reset`), but wired them to **throwaway**
`generate_token()` URLs with no persisted, single-use token behind them. Spec 104
finishes the three round trips — email verification, passwordless magic-link login,
and password reset — on one secure, hashed-at-rest, single-use, expiring token
store, and adds the frontend pages.

## The `auth_tokens` table (migration `a3c7e9d21f44`)

A dedicated table holds every link token, keyed by `token_hash` (sha256 of the
raw token; the raw value lives only inside the emailed URL):

| Column | Notes |
| --- | --- |
| `purpose` | `String(32)` + `CHECK (purpose IN ('email_verify','magic_login','password_reset'))` (`ck_auth_tokens_purpose`). A plain string + CHECK is simpler than a PG enum and matches the project's lightweight style. |
| `user_id` | FK → `users.id`, `ON DELETE CASCADE` (tokens die with the account). |
| `email` | CITEXT — the address the link was issued for, **bound at creation** so a later email change can't be confirmed by an old link. |
| `token_hash` | unique (`uq_auth_tokens_token_hash`) — the only lookup key. |
| `expires_at` / `consumed_at` | `created_at + per-purpose TTL`; `consumed_at` set on first use (single-use). |

Plus `ix_auth_tokens_user_purpose` (cheap "invalidate older tokens of this
purpose") and a partial `ix_auth_tokens_active` (`WHERE consumed_at IS NULL`,
forward-looking for a future expiry sweep that is out of scope).

### Why a new table, not the spec-59 pattern on `users`

Spec 59 stored the email-change token on the `users` row (one in-flight token per
user). That does not generalise to three concurrent purposes, multiple outstanding
magic links, or an `email` binding distinct from the account's current address. A
dedicated table is the right reuse-and-extend of the spec-59 *pattern*
(hash-at-rest + single-use + expiry), not a duplication. The spec-59 email-change
token **stays on `users`** — it was not migrated.

## 104 ↔ 103 ownership split

- **103 owns DELIVERY:** the `EmailSender` Protocol, SMTP/Resend/file transports,
  `send_email_job`, `EmailEnqueuer`, and the `email_verification` / `password_reset`
  template *renderers*. All reused **unchanged**.
- **104 owns the FLOWS:** the token store (`services/auth_tokens.py`), the flow
  services (`services/email_auth.py`), the request **and** callback endpoints, the
  non-enumeration semantics, the abuse limits, and the frontend pages. It
  **replaces** 103's throwaway tokens in the `register` and `forgot-password`
  enqueues with real persisted tokens.
- **One new template:** `magic_login` (`{user_name?, magic_url}`) added to
  `mailer/templates.py` and `_TEMPLATES`. The full inventory is now
  `project_invite`, `email_change_confirmation`, `email_verification`,
  `password_reset`, `magic_login`. Every interpolated value is HTML-escaped in the
  HTML body (spec-40 XSS rule), including the `href`.

## Security choices

- **Single lookup key, constant-time in effect:** `consume_token` looks a row up
  only by `token_hash` (an unknown token simply misses) and filters by `purpose`,
  so a verify token can never be redeemed at the reset callback. A `SELECT … FOR
  UPDATE` on the row prevents a double-spend race on two simultaneous clicks, and
  consumption happens **inside the same transaction** as the action it authorizes.
- **Uniform errors:** unknown / used / wrong-purpose tokens all raise the same
  `BadRequestError` ("Invalid or already-used link.") → 400; an expired-but-real
  token raises `GoneError` → 410 (so the user knows to request a fresh one). The
  request endpoints always return an identical `202`, enqueuing conditionally — no
  field or timing reveals whether an address exists.
- **One link at a time:** issuing a new token of a `(user, purpose)` sets
  `consumed_at` on all outstanding ones, bounding live tokens per user to one. The
  per-email+IP rate limits (reusing spec 52) bound the issuance rate; no separate
  counter is needed.
- **Ownership-proving side effects:** a successful magic-login and a successful
  password-reset both set `email_confirmed = True` (clicking a link proves inbox
  ownership). A reset additionally calls `refresh_store.revoke_user` to sign out
  **all** sessions (reuse of spec 07/08 revocation).
- **No raw token logged or persisted:** only the sha256 hash is stored; security
  events (`auth_token_issued`, `auth_token_consumed`, `magic_login_succeeded`,
  `password_reset_completed`, `auth_token_invalid`) carry `purpose`/`user_id`/
  `outcome` only.

## The `require-verified-email-to-login` toggle

`require_verified_email_to_login` defaults to **`false`**, so this spec adds
capability without changing the existing login contract (and without breaking
current tests). When an operator flips it on, `POST /auth/login` rejects an
unconfirmed user with the verification message, while the magic-link and reset
flows still let them in (both confirm the email). Flipping it on is an operator
decision.

## Token issuance seam

The four-line access+refresh issuance from `services/auth.login` was factored into
`issue_token_pair(token_service, refresh_store, user)` and is now called by both
credential login and the magic-link callback — the magic link produces the exact
same rotatable JWT pair as a password login, with no duplicated logic.

## Frontend

New `features/auth/` folder: request pages (`forgot-password`, `magic-link`,
`verify-email/resend`) and token callbacks (`verify-email`, `magic-link`,
`reset-password`), all reachable signed-out. Callbacks are **not** wrapped in
`PublicOnly` (a signed-in user may click a link in another tab); the pure request
pages may be. The magic-link callback reuses a new `loginWithTokenPair` auth-context
helper that shares the exact post-login path as `login`. The reset form reuses the
spec-06 `makePasswordSchema`; after a successful reset the user is directed to
`/login` (all tokens were revoked, so no auto-login).
