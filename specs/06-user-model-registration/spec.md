# Spec 06 — User Model & Registration (requirements)

## 1. Summary

This spec introduces the core `users` table and the public **registration**
endpoint. It defines the canonical user identity (UUID primary key,
case-insensitive unique email, argon2 password hash, display name, admin and
email-confirmation flags, timestamps) and the `POST /api/v1/auth/register`
endpoint with input validation and duplicate-email handling. It is the first
spec of Phase 1 and the foundation every later auth, project and collaboration
spec builds on.

## 2. Context & dependencies

- **Depends on:** spec **03** (async SQLAlchemy engine/session, `Base`
  declarative model, timestamp mixin, Alembic configured and runnable, test DB
  fixtures) and spec **04** (pytest + pytest-asyncio, an httpx `AsyncClient`
  fixture bound to the FastAPI app, transactional DB rollback per test).
- **Unlocks:** spec **07** (login uses this model + a password-verify function),
  spec **08** (guards resolve `User` rows), spec **09** (the register page calls
  this endpoint), and every spec that owns rows by `user_id`.
- **Affected areas:** backend (models, schemas, services, router), infra
  (Alembic migration, `.env.example`), docs (ADR for hashing choice).

## 3. Goals

- A `User` SQLAlchemy model and corresponding `users` table with the columns,
  constraints and indexes in §5.1.
- An Alembic migration that enables the Postgres `citext` extension and creates
  the table; `alembic upgrade head` and `alembic downgrade -1` both succeed.
- An argon2 password-hashing service exposing `hash_password()` and
  `verify_password()` (the latter is added now so spec 07 reuses it).
- `POST /api/v1/auth/register` that validates input, rejects duplicate emails,
  hashes the password, persists the user, and returns a safe public
  representation (never the hash) with status `201`.
- Email is normalised (trimmed, lower-cased) and stored/compared
  case-insensitively so `Alice@Ex.com` and `alice@ex.com` are the same account.
- Password strength rules enforced server-side (§5.2.3).

## 4. Non-goals (explicitly out of scope)

- Login, JWT issuance, refresh tokens, sessions, logout (spec 07/08).
- Auth guards / `get_current_user` / `require_admin` (spec 08).
- Email-confirmation sending/verification and password reset (later specs). The
  `email_confirmed` column exists but defaults to `false` and is never flipped
  here.
- Any frontend (spec 09).
- Rate limiting (groundwork is spec 08).
- Admin user management endpoints.

## 5. Detailed requirements

### 5.1 Data model

Enable the Postgres extension `citext` (in the migration, before table
creation). Table **`users`**:

| Column | Type | Constraints / Notes |
| --- | --- | --- |
| `id` | `UUID` | PK, server default `gen_random_uuid()` (pgcrypto) or app-generated `uuid4`; choose app-generated `uuid4` as default to avoid an extension dependency, but document the choice. NOT NULL. |
| `email` | `CITEXT` | NOT NULL, **UNIQUE**. Stored normalised (trimmed + lower-cased at the app layer). `citext` makes comparison case-insensitive at the DB layer too. |
| `hashed_password` | `VARCHAR(255)` | NOT NULL. Argon2 PHC-string (`$argon2id$...`). Never returned by any endpoint. |
| `display_name` | `VARCHAR(100)` | NOT NULL. 1–100 chars after trim. |
| `is_admin` | `BOOLEAN` | NOT NULL, default `false`. |
| `email_confirmed` | `BOOLEAN` | NOT NULL, default `false`. |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | NOT NULL, default `now()` (from the spec-03 timestamp mixin). |
| `updated_at` | `TIMESTAMP WITH TIME ZONE` | NOT NULL, default `now()`, ON UPDATE `now()` (mixin). |

**Indexes / constraints:**

- PK on `id`.
- `UNIQUE (email)` — name it `uq_users_email`. With `citext`, this is the
  case-insensitive uniqueness guarantee. (Do **not** add a separate
  `lower(email)` functional index; `citext` supersedes it.)
- No other indexes required this spec.

**Model notes:** reuse the spec-03 `Base` and timestamp mixin. Use SQLAlchemy
2.x typed `Mapped[...]` / `mapped_column(...)`. For the `email` column use the
SQLAlchemy-Postgres `CITEXT` type (`sqlalchemy.dialects.postgresql.CITEXT`). For
`id` use `Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ...)`.

**Migration expectations:** one new Alembic revision whose `upgrade()` runs
`op.execute("CREATE EXTENSION IF NOT EXISTS citext")` then creates the table;
`downgrade()` drops the table (leave the extension in place, or drop it —
document the choice). The migration must be deterministic and re-runnable in CI
on the test DB.

### 5.2 Backend / API

#### 5.2.1 Password-hashing service (`backend/.../auth/password.py` or similar)

Use **argon2** via `passlib`'s `CryptContext(schemes=["argon2"])` **or**
`argon2-cffi` directly. Pick one and be consistent; passlib is recommended for
the unified `verify` API. Use `argon2id`. Parameters: start from argon2-cffi
defaults (`time_cost=3`, `memory_cost=65536`, `parallelism=4`) but make them
overridable so tests can lower the cost (see §5.5 / Test plan) to stay within the
2-minute budget.

```python
def hash_password(plain: str) -> str: ...        # returns PHC string
def verify_password(plain: str, hashed: str) -> bool: ...  # constant-time-ish via lib
```

`verify_password` must never raise on a malformed hash; it returns `False`.

#### 5.2.2 Pydantic schemas (v2)

`RegisterRequest`:

| Field | Type | Rules |
| --- | --- | --- |
| `email` | `EmailStr` | Required. Pydantic `EmailStr` (pulls in `email-validator`). Normalised by the service before storage. |
| `password` | `str` | Required. 8–72 chars (72 is the historical bcrypt limit; keep it as a sane cap even though argon2 has no such limit, so the rule is documented and stable). Strength rules in §5.2.3. |
| `display_name` | `str` | Required. `min_length=1`, `max_length=100`, trimmed; reject if empty after trim. |

`UserPublic` (response):

| Field | Type |
| --- | --- |
| `id` | `UUID` |
| `email` | `str` |
| `display_name` | `str` |
| `is_admin` | `bool` |
| `email_confirmed` | `bool` |
| `created_at` | `datetime` |

`UserPublic` **must not** include `hashed_password`. Configure
`model_config = ConfigDict(from_attributes=True)`.

#### 5.2.3 Password strength rules

Validate in the schema (Pydantic field/`model_validator`) or a shared validator:

- Length 8–72.
- Must contain at least one letter and at least one digit (a pragmatic baseline;
  do not over-engineer).
- Must not be identical to, or contain, the local-part of the email (case-
  insensitive) — mirrors Overleaf's "password too similar to email" check.

On failure return `422` with a clear, field-scoped message (see error cases).

#### 5.2.4 Endpoint

**`POST /api/v1/auth/register`**

- **Auth:** none (public).
- **Request body:** `RegisterRequest` (JSON).
- **Success:** `201 Created`, body = `UserPublic`.
- **Behaviour:** normalise email (`email.strip().lower()`), run strength checks,
  check for an existing user with that email, hash the password, insert, commit,
  return the new user.

**Error cases:**

| Condition | Status | Body |
| --- | --- | --- |
| Malformed JSON / missing field / bad `EmailStr` / strength rule violated | `422` | FastAPI/Pydantic validation error envelope (the project's standard error shape from spec 02). |
| Email already registered (case-insensitive) | `409 Conflict` | `{ "detail": "An account with this email already exists." }` — **do not** leak which field or whether it was a near-match; return the same generic conflict. |
| Unexpected DB integrity error (race on the unique index) | `409 Conflict` | Same as above. Catch `IntegrityError`, roll back, return 409 (defends against the check-then-insert race). |

Email enumeration note: registration inevitably reveals existence via 409. That
is acceptable for registration (consistent with Overleaf and common practice);
do not add timing obfuscation here, but spec 07's login must not leak existence.

#### 5.2.5 Service layer

Put the create logic in a `UserService.register(...)` (or module function) that
the router calls, taking an `AsyncSession`. Keep the router thin. The service:
normalises email, hashes password, constructs the `User`, adds/flushes/commits,
and translates `IntegrityError` → a domain `EmailAlreadyExistsError` that the
router maps to 409.

### 5.3 Frontend / UI

None in this spec (spec 09).

### 5.4 Real-time / jobs / external integrations

None. Hashing is CPU-bound but fast enough at the chosen parameters to run inline
in the request; it does **not** go to ARQ. (Tests lower the cost to keep the
suite fast — see §5.5.)

### 5.5 Configuration

Add to `.env.example` (with safe defaults; argon2 params optional, only if you
choose to expose them):

| Var | Default | Purpose |
| --- | --- | --- |
| `ARGON2_TIME_COST` | `3` | argon2 iterations (optional knob). |
| `ARGON2_MEMORY_COST` | `65536` | KiB of memory (optional knob). |
| `ARGON2_PARALLELISM` | `4` | lanes (optional knob). |

Surface these through the existing Pydantic `Settings` (spec 02). Tests must be
able to set low-cost params (e.g. `time_cost=1, memory_cost=8, parallelism=1`)
via fixture/override so hashing is sub-millisecond and the suite stays fast. No
new secrets are required by this spec.

## 6. Overleaf reference (study only — never copy)

> Read these in `../overleaf/` to understand the approach. Inkstave code must be
> written independently.

- `services/web/app/src/Features/User/UserCreator.mjs` — how a user record is
  assembled before insert (email normalisation, default display/first name from
  the email local-part, default flags).
- `services/web/app/src/Features/User/UserRegistrationHandler.mjs` — the
  registration flow: validate email + password, look up by any email to detect
  duplicates, then create. Mirror the *sequence*, not the code.
- `services/web/app/src/Features/User/UserGetter.mjs` — lookup-by-email patterns
  (you only need "exists?" here).
- `services/web/app/src/Features/Authentication/AuthenticationManager.mjs` —
  password handling concepts: `validateEmail`, `validatePassword` (length
  min/max, "not too similar to email"), and `hashPassword`. **Overleaf uses
  bcrypt (`BCRYPT_ROUNDS`, 72-char truncation guard); Inkstave uses argon2.**
  Study the validation rules and the 72-char cap rationale only.

## 7. Acceptance criteria

1. **Given** a clean DB, **when** I `POST /api/v1/auth/register` with a valid new
   email, an 8–72 char password containing a letter and a digit, and a non-empty
   display name, **then** I get `201` and a `UserPublic` body containing `id`,
   `email` (normalised), `display_name`, `is_admin=false`, `email_confirmed=false`
   and `created_at`, and the body does **not** contain `hashed_password`.
2. **Given** that request succeeded, **when** I query the `users` row, **then**
   `hashed_password` is a `$argon2id$...` PHC string that is **not** the
   plaintext, and `verify_password(plaintext, stored_hash)` returns `True`.
3. **Given** an existing user `alice@ex.com`, **when** I register `Alice@EX.com`,
   **then** I get `409` with the generic conflict message and no second row is
   created.
4. **Given** a request whose password is shorter than 8 chars, longer than 72,
   missing a digit, missing a letter, or equal to/containing the email
   local-part, **then** I get `422` with a field-scoped message and no row is
   created.
5. **Given** a request with a malformed email or a missing field, **then** I get
   `422` and no row is created.
6. **Given** a display name that is empty or whitespace-only, **then** I get
   `422`.
7. **Given** two concurrent registrations for the same email that both pass the
   pre-check, **when** they race to insert, **then** exactly one succeeds with
   `201` and the other returns `409` (the `IntegrityError` is caught), with
   exactly one row in the table.
8. **Given** the migration, **when** I run `alembic upgrade head` on an empty DB,
   **then** the `citext` extension exists and the `users` table is created with
   the unique email constraint; `alembic downgrade -1` removes the table without
   error.

## 8. Test plan

> All tests combined across the project must keep the suite under 2 minutes.
> Argon2 cost is lowered in tests via settings override so hashing is trivial.

- **Unit (pytest):**
  - `hash_password`/`verify_password`: hash != plaintext; verify true for correct
    password, false for wrong password, false (no raise) for a garbage hash.
  - Password strength validator: table-driven cases for too-short, too-long,
    no-digit, no-letter, equals-email-local-part, and a valid password.
  - Email normalisation: mixed-case + surrounding whitespace → trimmed lowercase.
- **Integration (pytest + httpx + test DB):**
  - Happy-path register → `201`, response shape correct, no hash leaked, row
    present with hashed password.
  - Duplicate email (case-insensitive) → `409`, single row.
  - Validation failures (bad email, weak password, empty display name) → `422`,
    zero rows.
  - Race/integrity: simulate by inserting a row directly then registering the
    same email (or by patching the duplicate pre-check to no-op) and assert the
    `IntegrityError` path yields `409`.
  - Migration smoke: ensure the test DB created via Alembic has `citext` and the
    unique constraint (or assert the unique violation surfaces as 409).
- **E2E (Playwright):** none this spec.
- **Performance/budget note:** argon2 parameters are overridden to minimal cost
  in the test settings; no network, no ARQ, no real email. All DB work runs in
  the per-test transactional rollback fixture from spec 04.

## 9. Definition of Done

- [ ] All requirements in §5 implemented.
- [ ] All acceptance criteria in §7 pass.
- [ ] All tests in §8 written and green.
- [ ] Full suite runs in < 2 minutes.
- [ ] Lint/format/type-check clean (`ruff`, `ruff format`, `mypy`/`pyright`).
- [ ] New env vars documented in `.env.example`; ADR for hashing choice in `docs/`.
- [ ] No Overleaf code copied.
