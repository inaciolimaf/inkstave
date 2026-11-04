# Auth

Accounts, sign-in and the end of a session, plus first-run admin setup. A user registers with an
e-mail and password, or signs in by e-mail link, and gets a short JWT access token and a rotating
refresh token. Self-service settings (profile, editor preferences, password, e-mail, deletion) live
here too. From specs 06–08, 10, 59, 63, 92 and 104; setup and provisioning come from spec 57.

## Where it is

| File | Role |
|---|---|
| `backend/src/inkstave/modules/auth` | The auth module; `__init__.py` is its public interface |
| `backend/src/inkstave/modules/auth/deps.py` | `get_current_user`, `require_admin`, `get_optional_user`, `sse_user`, `authenticate_ws_token` |
| `backend/src/inkstave/modules/auth/credentials/tokens.py` | `TokenService`: sign and verify JWTs, previous-secret verification |
| `backend/src/inkstave/modules/auth/credentials/refresh_store.py` | `RefreshStore`: Redis records, families, per-user cutoff |
| `backend/src/inkstave/modules/auth/credentials/sessions.py` | `is_alive`, `end_every_session`, `revoke_session` |
| `backend/src/inkstave/modules/auth/credentials/auth_tokens.py` | `issue_token`, `consume_token`: e-mail link tokens |
| `backend/src/inkstave/modules/auth/credentials/password.py`, `backend/src/inkstave/modules/auth/credentials/opaque_tokens.py` | Argon2id `PasswordHasher`; `generate_token`, `hash_token` |
| `backend/src/inkstave/modules/auth/accounts/login.py` | Login, refresh, reuse detection, logout, `issue_token_pair` |
| `backend/src/inkstave/modules/auth/accounts/email_auth.py` | Verification, magic link, password reset |
| `backend/src/inkstave/modules/auth/accounts/account.py`, `backend/src/inkstave/modules/auth/accounts/users.py` | Profile, password, e-mail change, deactivation, deletion; registration, `normalise_email` |
| `backend/src/inkstave/modules/auth/throttling/limiter.py` | Per-scope limiter, `client_ip`, `hit_window` |
| `backend/src/inkstave/modules/auth/throttling/login_attempts.py` | `LoginThrottle` |
| `backend/src/inkstave/modules/auth/throttling/policies.py` | Named per-user policies (compile, agent, upload), `check_rate_limit` |
| `backend/src/inkstave/modules/auth/routes/auth.py`, `backend/src/inkstave/modules/auth/routes/users.py` | `/auth/*` and `/users/*` routes |
| `backend/src/inkstave/modules/admin` | Admin, health and setup routes, provisioning |
| `backend/src/inkstave/modules/admin/routes/setup.py`, `backend/src/inkstave/modules/admin/routes/admin.py`, `backend/src/inkstave/modules/admin/routes/health.py` | `/api/setup`; `/admin/ping`; probes and metrics (see the observability file) |
| `backend/src/inkstave/modules/admin/provisioning/admin.py`, `backend/src/inkstave/modules/admin/provisioning/migrate.py`, `backend/src/inkstave/modules/admin/provisioning/config_check.py`, `backend/src/inkstave/modules/admin/provisioning/seed.py` | `ensure_initial_admin`; `run_upgrade`; `validate_config`; `seed_demo` |
| `backend/src/inkstave/modules/admin/models.py` | `Ping`, table `pings` (`backend/migrations/versions/20260609_1531_d1d4079342b4_create_pings.py`); proved the migration workflow, no feature uses it |
| `backend/src/inkstave/cli.py` | `bootstrap-admin`, `seed`, `deactivate-user`, `check-config`, `doctor`, `migrate` |
| `frontend/src/modules/auth` | Login, register, link pages, `auth-context.tsx`, `setup/` |
| `frontend/src/modules/settings` | Settings page and the e-mail change confirm page |
| `frontend/src/lib/token-store.ts`, `frontend/src/lib/api-client.ts` | Access token in memory, refresh token in `localStorage`; refresh on 401, one in flight per tab |
| `backend/tests/integration/test_session_revocation.py`, `backend/tests/integration/test_login_attempts.py`, `backend/tests/integration/test_auth.py`, `backend/tests/integration/test_email_auth_flows_104.py`, `backend/tests/integration/test_auth_tokens_104.py`, `backend/tests/integration/test_account_api_59.py`, `backend/tests/integration/test_bootstrap_57.py` | Revocation; login limits; login and refresh; link flows; link tokens; settings; setup |

## Data

| Store | What | Created by |
|---|---|---|
| Postgres `users` | Identity, `hashed_password`, `is_admin`, `email_confirmed`, `session_version`, `is_active`, profile, pending e-mail change | `backend/migrations/versions/20260609_1607_2672f3100dca_create_users.py`, `backend/migrations/versions/20260610_1844_fda790a9deeb_user_settings_avatar_editor_preferences_.py`, `backend/migrations/versions/20261030_1000_b4d8f1a2c6e3_add_session_revocation.py` |
| Postgres `revoked_sessions` | `session_id` (primary key, no foreign key), `expires_at` (indexed) | `backend/migrations/versions/20261030_1000_b4d8f1a2c6e3_add_session_revocation.py` |
| Postgres `auth_tokens` | Link tokens: `purpose`, `user_id` (cascade), `email`, unique `token_hash`, `expires_at`, `consumed_at` | `backend/migrations/versions/20260612_1200_a3c7e9d21f44_create_auth_tokens.py` |
| Redis `refresh:{jti}` | JSON: `user_id`, `family_id`, `rotated`, `created_at`, `expires_at`. TTL is the refresh lifetime | `RefreshStore.store_refresh` |
| Redis `refresh_family_revoked:{family_id}` | Family marker, TTL is the refresh lifetime | `RefreshStore.revoke_family` |
| Redis `refresh_user_revoked_at:{user_id}` | Per-user cutoff timestamp, TTL is the refresh lifetime | `RefreshStore.revoke_user` |
| Redis `ratelimit:login:email:{email}`, `ratelimit:login:ip:{ip}`, `ratelimit:{scope}:{identity}` | Rate-limit counters | `LoginThrottle`, `rate_limit` |

Tokens:

| Token | Claims | Life |
|---|---|---|
| Access | `sub`, `type`, `is_admin`, `sv`, `sid`, `iss`, `iat`, `exp`, `jti` | `ACCESS_TOKEN_TTL_SECONDS` (900) |
| Refresh | `sub`, `type`, `family_id`, `sv`, `iss`, `iat`, `exp`, `jti` | `REFRESH_TOKEN_TTL_SECONDS` (1209600) |

`sid` and `family_id` hold the same value: the session id. It is minted at login and survives every
rotation. The `is_admin` claim is informational; `require_admin` reads the database.

`revoked_sessions` has one writer, `revoke_session`, and logout is its only production caller. It
also sweeps expired rows on each call. Its one reader is `is_alive`. Rows live for the refresh
lifetime, longer than any token of the session. The table is in Postgres so a Redis flush cannot bring
a logged-out session back.

## Routes

Errors use the envelope `{"error": {"type": ...}}`. Validation failures are 422 `validation_error`.
Every 401 is `unauthorized` with `WWW-Authenticate: Bearer`.

| Method and path | What it does | Errors |
|---|---|---|
| POST `/api/v1/auth/register` | Create an account, enqueue verification | 409 `conflict`, 429 `rate_limited` |
| POST `/api/v1/auth/login` | Issue a new session | 401 `unauthorized`, 429 `rate_limited` |
| POST `/api/v1/auth/refresh` | Rotate a refresh token | 401 `unauthorized`, 429 `rate_limited` |
| POST `/api/v1/auth/logout` | End the session of a refresh token; 200 even for a bad token | none |
| POST `/api/v1/auth/verify-email/resend` | 202, sends only to an unconfirmed user | 429 `rate_limited` |
| POST `/api/v1/auth/verify-email/confirm` | Spend the link, set `email_confirmed` | 400 `bad_request`, 410 `gone`, 429 `rate_limited` |
| POST `/api/v1/auth/magic-link` | 202, sends only if the user exists | 429 `rate_limited` |
| POST `/api/v1/auth/magic-link/callback` | Spend the link, return a token pair | 400 `bad_request`, 410 `gone`, 429 `rate_limited` |
| POST `/api/v1/auth/forgot-password` | 202, sends only if the user exists | 429 `rate_limited` |
| POST `/api/v1/auth/reset-password` | Spend the link, set the password, end every session | 400 `bad_request`, 410 `gone`, 429 `rate_limited` |
| GET `/api/v1/users/me` | Own profile (`UserMe`) | 401 `unauthorized` |
| PATCH `/api/v1/users/me` | Update `display_name`, `avatar_url` | 401 `unauthorized` |
| DELETE `/api/v1/users/me` | Hard delete after password and `confirm: true` | 401 `unauthorized`, 422 |
| PUT `/api/v1/users/me/editor-preferences` | Replace `theme`, `font_size`, `keymap`, `autocomplete` (boolean, default `true`: the LaTeX completion popup) | 401 `unauthorized` |
| POST `/api/v1/users/me/change-password` | New password, end every session | 400 `bad_request`, 401 `unauthorized`, 429 `rate_limited` |
| POST `/api/v1/users/me/change-email` | Stage an e-mail change, 202 | 400 `bad_request`, 401 `unauthorized`, 409 `conflict` |
| POST `/api/v1/users/confirm-email-change` | Unauthenticated; apply the change | 400 `bad_request`, 409 `conflict`, 410 `gone` |
| GET `/api/v1/admin/ping` | `{"ok": true}`, the only admin route | 401 `unauthorized`, 403 `forbidden` |
| GET `/api/setup/status` | `{"needs_setup": bool}` | none |
| POST `/api/setup/admin` | Create the first admin | 409 `conflict` |

## How it works

**Sign in.** `login` calls `authenticate_user`. An unknown e-mail still runs Argon2 against
`_DUMMY_HASH`, so timing does not reveal it. An inactive account with the right password gets the same
uniform 401. With `REQUIRE_VERIFIED_EMAIL_TO_LOGIN` on, an unconfirmed user gets 401 "Please verify
your email first." `issue_token_pair` mints a new `family_id`, an access token carrying it as `sid`,
and a refresh token stored in Redis. Magic-link sign-in uses the same function.

**Refresh and rotation.** `refresh_tokens` decodes the token, then `_validate_refresh` checks in order:
record exists and family not revoked; record not `rotated`; per-user cutoff. It then loads the user
and runs `is_alive`. On success `rotate_refresh` marks the old record, and a new pair is issued in the
same family, so the session id holds.

**Reuse detection.** A `rotated` record presented again means the token was replayed. `revoke_family`
writes the Redis marker and the route answers 401 "Refresh token reuse detected; session revoked."
Every refresh token of the family is dead from then on. No `revoked_sessions` row is written, so the
family's access tokens keep working (see Points of attention).

**The liveness check.** `is_alive` runs behind every token path: `_resolve_user` (HTTP guards, SSE,
WebSocket admission) and refresh. It refuses when `is_active` is false, when `sv` differs from
`session_version`, or when `sid` (or `family_id`) has a `revoked_sessions` row. That is one extra
primary-key lookup per request.

**Tokens from before these claims.** A missing `sv` counts as 0, so a deploy signs nobody out. A missing
`sid` skips the revocation lookup, so logout cannot reach it. Old refresh tokens rotate into the new claims.

**How a session ends.**

| Event | `session_version` | `revoked_sessions` | Redis | Reach |
|---|---|---|---|---|
| Logout | no | row for this `sid` | family marker | This device, all its access and refresh tokens |
| Reuse detected | no | no | family marker | Refresh tokens of the family only |
| Password change | +1 | no | user cutoff | Every session, the caller's included |
| Password reset | +1 | no | user cutoff | Every session |
| Deactivation | +1, and `is_active` false | no | none | Every session; refresh dies in `is_alive` |
| Account deletion | row gone | no | user cutoff | Every session; the user lookup fails |

**Logout.** `logout` decodes the refresh token, then calls `revoke_family` and `revoke_session`. A token
that does not decode, expired ones included, is a silent no-op. Any member of the family works, a rotated one too.

**Password change.** `change_password` verifies the current password, refuses a password containing the
e-mail local part, hashes off the event loop, calls `end_every_session`, then `revoke_user`. The
frontend then logs out (`frontend/src/modules/settings/PasswordSection.tsx`).

**Deactivation.** `python -m inkstave.cli deactivate-user --email <address>` calls `deactivate_account`.
No route exists. Exit code 1 for an unknown address. Undoing it is manual SQL:
`UPDATE users SET is_active = true`. Old tokens stay dead afterwards because `session_version` moved.

**Login limits.** `get_login_throttle` builds a `LoginThrottle` for `client_ip`. `attempt` wraps the
login:

1. `_count` increments the IP counter, then the e-mail counter, before Argon2 runs. Over the limit
   raises `RateLimitError`: 429 `rate_limited` with `Retry-After` (remaining window) and
   `X-RateLimit-Remaining: 0`. The attempt is counted first so a concurrent burst cannot pass the
   check while its verifications are running.
2. Only `InvalidCredentialsError` leaves the attempt counted.
3. Any other outcome runs `_forgive`: delete the e-mail counter, decrement the IP counter. Success
   does not clear the IP counter, or one valid account would reset an attacker's allowance.

The e-mail is normalised, so case does not dodge the counter. The per-IP limit applies only when
`TRUST_PROXY_HEADERS` is true or the peer address is public (`ipaddress.is_global`). A private peer
without trusted headers is the reverse proxy, shared by every user, so the per-IP limit stands down
and only the per-e-mail one applies. A Redis failure in the throttle logs a warning, increments
`inc_rate_limit_error("login")` and allows the attempt.

**Other limits.** `rate_limit(scope)` is a fixed window, also failing open. `register`, `verify_email`
and `magic_link` key on the pair IP and body `email` when one is present; their token-only callbacks key
on IP. `refresh`, `forgot_password` and `reset_password` key on IP. Change-password uses
`RATE_LIMIT_AUTH_PASSWORD` per user. Without an authenticated user it keys on the raw peer, ignoring
`client_ip`.

**E-mail link tokens.** `issue_token` marks older active tokens of the same user and purpose as consumed,
then stores the SHA-256 of a 32-byte token. The raw value goes only into the URL. `consume_token`
selects by hash and purpose `FOR UPDATE`; unknown, used and wrong-purpose tokens all answer 400 "Invalid
or already-used link." An expired one answers 410. Spending happens in the caller's unit of work, so a
later failure, such as a weak new password, rolls the spend back and the link still works.

- **Verification.** `register` and `/verify-email/resend` send `{FRONTEND_URL}/verify-email?token=`.
  `confirm_email_verification` refuses if the address changed since the link was sent.
- **Magic link.** `{FRONTEND_URL}/magic-link?token=`. `complete_magic_login` refuses an address change or
  an inactive account, confirms the e-mail and issues a pair.
- **Password reset.** `{FRONTEND_URL}/reset-password?token=`. `complete_password_reset` re-validates
  strength (the schema alone is not trusted here), confirms the e-mail and ends every session.

**E-mail change.** It does not use `auth_tokens`. `start_email_change` needs the current password, stores
`pending_email` plus the token hash on `users`, and mails `{FRONTEND_URL}/settings/confirm-email?token=`
to the new address. The active e-mail is unchanged until `confirm_email_change`, which swaps it, sets
`email_confirmed`, clears the pending fields and maps a late unique violation to 409. Sessions continue.

**WebSocket entry point.** There is no ticket. The client puts the access JWT in `?token=` on
`/ws/collab/projects/{project_id}/documents/{document_id}`
(`frontend/src/modules/collab/InkstaveWsProvider.ts`). `_admit` in
`backend/src/inkstave/modules/collab/ws/router.py` calls `authenticate_ws_token` before `accept`, so the
check equals `get_current_user`. Failure closes with 4401. A missing token closes with 4401 too.
Authorization and the room are in the collab file.
`sse_user` takes the Bearer header or `?access_token=`, for compile, agent and project import events.

**First admin.** Two paths reach `ensure_initial_admin`: `POST /api/setup/admin` and `inkstave
bootstrap-admin` (`INKSTAVE_ADMIN_EMAIL`, `INKSTAVE_ADMIN_PASSWORD`, or a TTY prompt). It takes
`pg_advisory_xact_lock`, returns `None` if any admin exists, and otherwise creates one. The route turns
`None` into 409. `seed_demo` creates `demo@example.com` and a multi-file project, is idempotent, and
refuses `environment == "prod"` without `--force`. `run_upgrade` runs Alembic under a session
advisory lock so concurrent starts run it once. `validate_config` backs `check-config` and `doctor`.

## Rules and guarantees

| Invariant | Test |
|---|---|
| Token types do not cross; a retired secret still verifies | `backend/tests/unit/test_tokens.py::test_decode_rejects_wrong_type`, `backend/tests/unit/test_tokens.py::test_decode_accepts_a_previous_secret_during_rotation` |
| Production refuses weak current or previous secrets | `backend/tests/unit/test_production_secrets.py::test_production_refuses_a_bad_current_secret`, `backend/tests/unit/test_production_secrets.py::test_production_refuses_a_bad_previous_secret` |
| Wrong password and unknown e-mail look the same; refresh rotates | `backend/tests/integration/test_auth.py::test_login_failures_are_uniform`, `backend/tests/integration/test_auth.py::test_refresh_rotates_tokens` |
| Replaying a rotated token kills the family's refresh tokens | `backend/tests/integration/test_auth.py::test_refresh_reuse_revokes_family`, `backend/tests/integration/test_guards.py::test_revoked_family_cannot_mint_access` |
| Logout kills a copied access token | `backend/tests/integration/test_session_revocation.py::test_logout_kills_the_copied_access_token` |
| Logout leaves other devices in | `backend/tests/integration/test_session_revocation.py::test_logout_leaves_other_devices_signed_in` |
| `sid` is stable across rotations | `backend/tests/integration/test_session_revocation.py::test_logout_after_a_refresh_still_kills_the_first_access_token` |
| Logout is idempotent and sweeps expired rows | `backend/tests/integration/test_session_revocation.py::test_logging_out_twice_is_idempotent`, `backend/tests/integration/test_auth.py::test_logout_with_invalid_token_is_idempotent`, `backend/tests/integration/test_session_revocation.py::test_logout_sweeps_expired_rows` |
| Password change and reset kill every token | `backend/tests/integration/test_session_revocation.py::test_change_password_kills_every_access_token`, `backend/tests/integration/test_session_revocation.py::test_password_reset_kills_every_access_token` |
| Deactivation ends access, refresh, login and magic link; `is_active` alone refuses; the CLI works by e-mail | `backend/tests/integration/test_session_revocation.py::test_deactivation_ends_access_refresh_and_login`, `backend/tests/integration/test_session_revocation.py::test_deactivated_account_cannot_use_a_magic_link`, `backend/tests/integration/test_session_revocation.py::test_is_active_alone_is_enough_to_refuse_a_token`, `backend/tests/integration/test_session_revocation.py::test_cli_deactivates_by_email` |
| Tokens without `sv` live until the version moves; old refresh tokens rotate into the new claims | `backend/tests/integration/test_session_revocation.py::test_pre_deploy_tokens_keep_working_until_the_version_moves`, `backend/tests/integration/test_session_revocation.py::test_pre_deploy_refresh_token_rotates_into_the_new_claims` |
| WebSocket and SSE admission refuse a revoked session | `backend/tests/integration/test_session_revocation.py::test_websocket_and_sse_paths_refuse_a_revoked_session` |
| `is_admin` comes from the database, not the token | `backend/tests/integration/test_guards.py::test_admin_check_is_db_authoritative` |
| 429 carries `Retry-After` and `rate_limited`; the right password is refused too | `backend/tests/integration/test_login_attempts.py::test_the_right_password_is_refused_once_the_email_limit_is_reached` |
| Only wrong passwords count | `backend/tests/integration/test_login_attempts.py::test_successful_logins_are_not_counted` |
| Success clears the e-mail counter, not the IP counter | `backend/tests/integration/test_login_attempts.py::test_success_resets_the_email_counter`, `backend/tests/integration/test_login_attempts.py::test_success_does_not_clear_the_ip_counter` |
| A concurrent burst cannot pass the limit | `backend/tests/integration/test_login_attempts.py::test_a_concurrent_burst_cannot_outrun_the_limit` |
| The per-IP limit stands down for a private peer, not a public one | `backend/tests/integration/test_login_attempts.py::test_behind_an_untrusted_proxy_the_ip_limit_stands_down`, `backend/tests/integration/test_login_attempts.py::test_a_peer_that_is_no_public_address_never_touches_the_ip_counter`, `backend/tests/integration/test_login_attempts.py::test_a_public_peer_is_limited_without_trusted_headers` |
| The proxy header is read only when trusted | `backend/tests/unit/test_rate_limit.py::test_client_ip_uses_proxy_header_only_when_trusted` |
| A limiter outage does not lock users out | `backend/tests/integration/test_guards.py::test_login_rate_limit_fails_open_when_redis_errors` |
| Link tokens are stored hashed | `backend/tests/integration/test_auth_tokens_104.py::test_issue_stores_only_the_hash_and_expiry` |
| The newest link supersedes older ones | `backend/tests/integration/test_auth_tokens_104.py::test_issue_invalidates_older_same_purpose_tokens` |
| Link tokens are single-use, bound to a purpose, and 410 when expired | `backend/tests/integration/test_auth_tokens_104.py::test_consume_happy_path_then_single_use`, `backend/tests/integration/test_auth_tokens_104.py::test_consume_wrong_purpose_is_bad_request`, `backend/tests/integration/test_auth_tokens_104.py::test_consume_expired_is_gone_and_not_consumed` |
| Raw tokens never reach the logs | `backend/tests/integration/test_auth_tokens_104.py::test_raw_token_never_logged` |
| A double click cannot spend a link twice (`FOR UPDATE`) | No dedicated test |
| A weak reset password leaves the link usable | No dedicated test; the 400 itself is `backend/tests/integration/test_email_auth_flows_104.py::test_reset_password_weak_is_400` |
| Link requests do not reveal accounts | `backend/tests/integration/test_email_auth_flows_104.py::test_magic_link_unknown_is_non_enumerating`, `backend/tests/integration/test_email_auth_flows_104.py::test_forgot_password_unknown_is_non_enumerating`, `backend/tests/integration/test_email_auth_flows_104.py::test_resend_unknown_user_enqueues_zero` |
| E-mail change waits for confirmation, is single-use, and 410 when expired | `backend/tests/integration/test_account_api_59.py::test_change_email_then_confirm`, `backend/tests/integration/test_account_api_59.py::test_confirm_expired_token_is_gone` |
| Deletion needs `confirm` and the password, cascades and ends sessions | `backend/tests/integration/test_account_api_59.py::test_delete_requires_confirm_and_correct_password`, `backend/tests/integration/test_account_api_59.py::test_delete_account_cascades_and_revokes` |
| Setup locks after the first admin | `backend/tests/integration/test_bootstrap_57.py::test_setup_status_then_admin_then_locked` |
| Two simultaneous setups create one admin | No dedicated test; the sequential case is `backend/tests/integration/test_bootstrap_57.py::test_setup_admin_second_attempt_creates_nothing` |
| Demo seed refuses production and is idempotent | `backend/tests/unit/test_bootstrap_57.py::test_seed_demo_refuses_in_production`, `backend/tests/integration/test_bootstrap_57.py::test_seed_demo_is_idempotent_in_dev` |

## Settings

Names from `backend/src/inkstave/core/config/groups.py`, as environment variables.

| Variable | Default | Effect |
|---|---|---|
| `JWT_SECRET` | required | Signing key; production refuses a weak one |
| `JWT_SECRET_PREVIOUS` | empty | Retired keys, verify only |
| `JWT_ALGORITHM`, `JWT_ISSUER` | `HS256`, `inkstave` | |
| `ACCESS_TOKEN_TTL_SECONDS`, `REFRESH_TOKEN_TTL_SECONDS` | `900`, `1209600` | Refresh TTL is also the life of Redis markers and `revoked_sessions` rows |
| `ARGON2_TIME_COST`, `ARGON2_MEMORY_COST`, `ARGON2_PARALLELISM` | `3`, `65536`, `4` | |
| `RATE_LIMIT_ENABLED` | `true` | Turns off all these limits |
| `RATE_LIMIT_AUTH_LOGIN`, or `RATE_LIMIT_LOGIN` | `10/300` | Wrong passwords per e-mail |
| `RATE_LIMIT_LOGIN_IP` | `50/300` | Wrong passwords per IP |
| `RATE_LIMIT_REGISTER`, `RATE_LIMIT_REFRESH` | `5/3600`, `30/300` | |
| `RATE_LIMIT_AUTH_PASSWORD` | `5/3600` | Change-password and forgot-password |
| `RATE_LIMIT_VERIFY_EMAIL`, `RATE_LIMIT_MAGIC_LINK`, `RATE_LIMIT_RESET_PASSWORD` | `5/3600`, `5/3600`, `10/3600` | |
| `TRUST_PROXY_HEADERS`, `TRUSTED_PROXY_HEADER` | `false`, `X-Forwarded-For` | Read the client IP from that header |
| `FRONTEND_URL` | `http://localhost:5173` | Base of every link in these e-mails |
| `EMAIL_VERIFICATION_TOKEN_TTL`, `EMAIL_CHANGE_TOKEN_TTL`, `MAGIC_LOGIN_TOKEN_TTL`, `PASSWORD_RESET_TOKEN_TTL` | `86400`, `86400`, `600`, `3600` | |
| `REQUIRE_VERIFIED_EMAIL_TO_LOGIN` | `false` | Password login only; link flows confirm the e-mail |

## Points of attention

- **Reuse does not reach access tokens.** Reuse revokes the family in Redis only. `_validate_refresh`
  raises, so the unit of work would roll back any `revoked_sessions` row, and the code writes none.
  An attacker's access token runs out its TTL, up to 15 minutes by default.
- **Open connections survive revocation.** `is_alive` runs when a WebSocket or SSE stream opens, never
  during one. No token expiry check runs on an open stream either. Logout, password change, deactivation
  and account deletion leave open collaboration sockets and event streams running until they disconnect.
  A socket with write access keeps writing.
- **`X-Forwarded-For` is spoofable with trust on.** `client_ip` takes the first entry.
  `infra/nginx/default.conf` uses `$proxy_add_x_forwarded_for`, which appends, so the first entry is
  whatever the client sent. An attacker can rotate it to get a fresh per-IP counter on each request.
  The per-e-mail limit still holds; IP-keyed limits do not. `TRUST_PROXY_HEADERS=true` also skips
  the public-address test, so a spoofed value always counts as a key.
- **Only login stands down behind a proxy.** With `TRUST_PROXY_HEADERS=false` behind a proxy, every
  `rate_limit(scope)` key uses the proxy's address. `refresh` (30/300), `forgot_password` (5/3600) and
  `reset_password` then share one counter across all users.
- **Rotation is not atomic.** `get_refresh` and `rotate_refresh` are separate Redis calls, so two
  concurrent refreshes can both pass. `frontend/src/lib/api-client.ts` keeps one refresh in flight per
  tab, but tabs share one `localStorage` token. Two tabs refreshing one after the other replay it and
  trigger reuse detection, which signs that browser out.
- **Password-reset links survive an e-mail change.** Verification and magic link compare `token.email`
  to the current address; `complete_password_reset` does not. A link sent to the old address stays valid
  until its TTL. Nothing notifies the old address of a change either. No sessions end on an e-mail change.
- **Change-password says less than it does.** The route summary and response say "Other sessions were
  signed out". The code ends every session, the caller's included, and the test asserts this.
- **Redis outage.** The limiters fail open, but login and refresh do not: `store_refresh` and `get_refresh`
  have no fallback, so login fails anyway. `test_login_rate_limit_fails_open_when_redis_errors` breaks
  only `eval` and `incr`. A Redis flush drops every refresh record, reuse marker and user cutoff; refresh
  then fails with 401 for all sessions, while `sv` and `revoked_sessions` hold.
- **Requests with no throttle.** `logout`, `change-email`, `confirm-email-change`, `DELETE /users/me` and
  `/api/setup/admin` have no limit. The two re-auth routes verify a password with no attempt limit.
- **Setup can reopen.** `admin_exists` counts `is_admin` rows. Deleting the last admin through `DELETE
  /users/me` reopens `POST /api/setup/admin`, which is public. On a fresh deployment the first caller
  becomes admin. A deactivated admin still counts as existing. There is no route or command to
  promote an admin, or to reactivate a user. `ensure_initial_admin` hashes on the event loop, unlike
  every other path.
- **Registration is open** and reveals existing addresses with 409, unlike the link flows. No setting closes it.
- **Reset ignores `is_active`.** A deactivated user can complete a reset. The password changes, the
  account stays locked. `request_magic_login` also mails inactive users; the callback then refuses.
- **`auth_tokens` has no sweep.** Rows stay until the user is deleted.
- **Tokens in URLs.** WebSocket and SSE carry the access JWT in the query string, so any log that records
  URLs records a live token. See the security file.
- **English only.** Error messages, `MessageResponse.detail` and every template in
  `backend/src/inkstave/infra/mailer/templates.py` are English; nothing reads `Accept-Language`. A
  Portuguese user sees translated frontend strings where the page maps a status code, for example
  `login.tooManyAttempts`, and English where it shows the backend detail.
