# ADR 0005 — Password hashing (argon2id) and case-insensitive email (citext)

- **Status:** Accepted
- **Date:** 2026-06-09
- **Context spec:** 06 — User Model & Registration

## Context

Spec 06 introduces the `users` table and registration. Two decisions outlive
this spec and are recorded here: how passwords are hashed, and how email
uniqueness is made case-insensitive.

## Decisions

### 1. Password hashing: argon2id via `argon2-cffi`

- We hash passwords with **argon2id** using `argon2-cffi`'s `PasswordHasher`,
  wrapped in a tiny `inkstave.auth.password.PasswordHasher` exposing
  `hash(plain)` and `verify(plain, hashed)`.
- **Why argon2 over bcrypt** (Overleaf uses bcrypt): argon2id is the modern,
  memory-hard, OWASP-recommended default; it has no 72-byte truncation pitfall.
  We chose `argon2-cffi` directly over `passlib` because passlib is in
  maintenance mode and a direct, well-typed dependency is simpler.
- **Parameters** are read from settings (`ARGON2_TIME_COST=3`,
  `ARGON2_MEMORY_COST=65536`, `ARGON2_PARALLELISM=4` — the library defaults) and
  the hasher is built via the `get_password_hasher` dependency, so **tests lower
  the cost** (`t=1, m=8, p=1`) to keep hashing sub-millisecond and the suite
  fast.
- `verify()` **never raises** — a malformed/garbage hash or wrong password
  returns `False`. This keeps spec 07's login path (which reuses `verify`) free
  of error handling around bad stored values.
- **72-char password cap:** kept as a documented `RegisterRequest` rule even
  though argon2 has no such limit, so the bound is stable and explicit.

### 2. Case-insensitive email via `citext`

- The `email` column uses Postgres **`citext`** (the extension is created in the
  migration before the table) and a `UNIQUE` constraint `uq_users_email`. This
  gives case-insensitive comparison and uniqueness **at the DB layer**, so a
  race that bypasses the app-level pre-check still cannot create a duplicate.
- The app **also** normalises email (`strip().lower()`) before storing, so the
  stored value is canonical and the chosen path is explicit. We do **not** add a
  separate `lower(email)` functional index — `citext` supersedes it.
- **UUID PK** stays app-generated (`uuid4`, via the spec-03 mixin) — no
  `pgcrypto`/`gen_random_uuid()` dependency (consistent with ADR 0003).
- **Downgrade** drops the `users` table but **leaves the `citext` extension** in
  place: other objects may come to depend on it, and dropping an extension is
  rarely what a rollback intends.

### 3. Conflict response shape

A duplicate email returns **409** using the project's **uniform error envelope**
(`{"error": {"type": "conflict", "message": "An account with this email already
exists."}}`) via an `EmailAlreadyExistsError(ConflictError)`. The spec's table
sketched a bare `{"detail": ...}` body, but spec 02 established the single error
envelope as a cross-cutting public contract (asserted by tests and OpenAPI); we
keep that invariant and surface the same generic message. The message is generic
(does not reveal which field/near-match), per the spec.

The duplicate pre-check and the `IntegrityError` fallback both map to the same
409, defending against the check-then-insert race (verified by a test that
patches the pre-check to miss).

## Consequences

- New runtime deps: `argon2-cffi`, `email-validator` (for Pydantic `EmailStr`).
- New settings/env vars: `ARGON2_TIME_COST`, `ARGON2_MEMORY_COST`,
  `ARGON2_PARALLELISM` (documented in `.env.example`).
- Registration hashing runs **inline** in the request (fast at these params); it
  does not go to ARQ.
- Spec 07 (login) reuses `PasswordHasher.verify`; spec 08 (guards) resolves
  `User` rows.

## Alternatives considered

- **bcrypt** (Overleaf's choice) — fine but older; the 72-byte cap is a footgun.
  Rejected in favour of argon2id.
- **passlib `CryptContext`** — unified API, but maintenance-mode and an extra
  abstraction; rejected for a direct `argon2-cffi` wrapper.
- **`lower(email)` unique index instead of citext** — works, but citext is
  cleaner and makes every comparison case-insensitive without remembering to
  wrap in `lower()`.
- **Bare `{"detail": ...}` 409 body** — would break the uniform envelope
  contract; rejected.
