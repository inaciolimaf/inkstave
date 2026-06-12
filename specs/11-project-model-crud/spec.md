# Spec 11 — Project model & CRUD API (requirements)

## 1. Summary

This spec introduces the **Project** entity — the top-level container a user owns
and works in — together with a REST CRUD API under `/api/v1/projects`. It
delivers the persistence model, Pydantic schemas, a service/repository layer,
ownership-scoped endpoints, and an Alembic migration. It is the foundation that
the file tree (12), document content (13) and binary storage (14) all attach to.

## 2. Context & dependencies

- **Depends on:**
  - **06** — `User` model and `users` table (owner FK target, password hashing).
  - **08** — `get_current_user` dependency, protected-route plumbing, 401 handling.
  - **02** — FastAPI app factory, settings, structured error envelope.
  - **03** — async SQLAlchemy session dependency, `Base`, Alembic env, UUID/`TimestampMixin` conventions.
  - **04** — pytest fixtures (test DB per-session, async client, auth helpers).
- **Unlocks:**
  - **12** — `tree_entities` reference `projects.id`.
  - **13** — `documents` rows belong to a project's doc entity.
  - **14** — binary files are keyed per project.
  - **16** — the project dashboard UI consumes this API.
- **Affected areas:** backend (models, schemas, services, routers, migration),
  docs (ADR for delete strategy).

## 3. Goals

- A `projects` table with a UUID PK, owner FK, name, timestamps, and an optional
  `root_doc_id` (nullable, no FK yet — the docs table does not exist until 13).
- Endpoints: create, list (owner's projects only), get one, rename, delete.
- Every endpoint requires authentication and enforces ownership: a user can only
  see/modify their own projects; another user's project is **404** (not 403), to
  avoid leaking existence.
- Soft delete (see §5.1 decision) with list/get excluding soft-deleted rows.
- One Alembic migration that creates the table and its indexes.
- Full unit + integration test coverage; suite stays well under 2 minutes.

## 4. Non-goals (explicitly out of scope)

- File tree contents: folders, documents, files (spec 12).
- Document text storage and `root_doc_id` foreign-key wiring (spec 13).
- Binary uploads (spec 14).
- Sharing / collaborators / roles / non-owner access (specs 33, 34).
- Project duplication, archiving, trashing-with-restore UI, templates.
- Any frontend (spec 16).

## 5. Detailed requirements

### 5.1 Data model

**Decision — soft delete.** Projects use a **soft delete**: a nullable
`deleted_at` timestamp column. Rationale: (a) later specs (history 36–38,
sharing 33) and the dashboard's "trash"/restore UX are easier to add without a
second migration; (b) it avoids orphaning child rows (tree entities, documents,
files, compile outputs) at this stage — a hard cascade delete would be
destructive and is deferred to a dedicated purge job in a later spec. The CRUD
`DELETE` endpoint performs a soft delete (sets `deleted_at = now()`). All
read/list/rename operations filter out rows where `deleted_at IS NOT NULL`. A
hard purge is **out of scope** here. Record this in `docs/adr/0011-project-delete.md`.

#### Table `projects`

| Column | Type | Constraints | Notes |
| --- | --- | --- | --- |
| `id` | `UUID` | PK, default `gen_random_uuid()` (server default via `uuid_generate_v4`/`gen_random_uuid`, matching spec 03's convention) | Project identifier. |
| `owner_id` | `UUID` | `NOT NULL`, FK → `users.id` `ON DELETE CASCADE` | The owning user. |
| `name` | `VARCHAR(255)` | `NOT NULL`, `CHECK (char_length(trim(name)) > 0)` | Human title; trimmed, 1–255 chars. |
| `root_doc_id` | `UUID` | `NULL` | The "main" document's tree-entity id. **No FK yet** (target table arrives in 12/13). Wired in a later spec. |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL`, default `now()` | From the shared `TimestampMixin` (spec 03). |
| `updated_at` | `TIMESTAMPTZ` | `NOT NULL`, default `now()`, `ON UPDATE now()` (via SQLAlchemy `onupdate`) | Bumped on rename. |
| `deleted_at` | `TIMESTAMPTZ` | `NULL` | Non-null ⇒ soft-deleted. |

**Indexes:**

- PK on `id`.
- `ix_projects_owner_id` on `owner_id` — supports the list query.
- Composite partial index `ix_projects_owner_active` on `(owner_id, updated_at DESC)`
  `WHERE deleted_at IS NULL` — supports the default "my active projects, recent
  first" listing efficiently.

**Relationships (SQLAlchemy):**

- `Project.owner` → `User` (many-to-one); `User.projects` back-populates
  (lazy `selectin` not required here; keep `lazy="raise"`/default per spec 03
  conventions to avoid accidental N+1).
- No relationship to tree entities yet (added in 12).

**Migration:** one Alembic revision `xxxx_create_projects` that creates the
table, the FK, the check constraint and all three indexes. Downgrade drops them.
The migration must be reversible and must `op.create_index(..., postgresql_where=...)`
for the partial index.

### 5.2 Backend / API

All routes are mounted under `/api/v1/projects` (router `app/api/v1/projects.py`,
included by the v1 API router from spec 02). **All routes require a valid access
token** via the `get_current_user` dependency (spec 08). Unauthenticated calls
return **401** with the standard error envelope.

**Pydantic schemas (`app/schemas/project.py`, Pydantic v2):**

```
ProjectCreate:
    name: str  # min_length 1 after strip, max_length 255; whitespace-trimmed by validator

ProjectRename:
    name: str  # same constraints as create

ProjectRead:
    id: UUID
    owner_id: UUID
    name: str
    root_doc_id: UUID | None
    created_at: datetime
    updated_at: datetime
    # deleted_at is NOT exposed in responses
    model_config = ConfigDict(from_attributes=True)

ProjectList:
    items: list[ProjectRead]
    total: int
```

#### Endpoints

| # | Method | Path | Auth | Request body | Success | Response body |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `POST` | `/api/v1/projects` | required | `ProjectCreate` | `201 Created` | `ProjectRead` |
| 2 | `GET` | `/api/v1/projects` | required | — (query: `limit` 1–100 default 50, `offset` ≥0 default 0) | `200 OK` | `ProjectList` |
| 3 | `GET` | `/api/v1/projects/{project_id}` | required | — | `200 OK` | `ProjectRead` |
| 4 | `PATCH` | `/api/v1/projects/{project_id}` | required | `ProjectRename` | `200 OK` | `ProjectRead` |
| 5 | `DELETE` | `/api/v1/projects/{project_id}` | required | — | `204 No Content` | empty |

**Behaviour details:**

1. **Create** — sets `owner_id = current_user.id`, trims `name`, persists, returns
   `201` with the created `ProjectRead`. `root_doc_id` is `null` at creation.
2. **List** — returns only the caller's **non-deleted** projects, ordered by
   `updated_at DESC, id DESC` (stable tiebreak), paginated. `total` is the count
   of the caller's non-deleted projects (ignoring `limit`/`offset`).
3. **Get** — returns the caller's non-deleted project by id.
4. **Rename (PATCH)** — updates `name` (trimmed), bumps `updated_at`, returns the
   updated project. Only the owner may rename.
5. **Delete** — soft-deletes (sets `deleted_at = now()`). Idempotent-ish: a
   second delete of an already-deleted project returns **404** (the row is no
   longer visible). Returns `204` with no body.

**Error cases (standard error envelope from spec 02):**

| Condition | Status | `error.code` |
| --- | --- | --- |
| No / invalid / expired token | `401` | `unauthorized` |
| `project_id` not a valid UUID | `422` | `validation_error` |
| Project not found, not owned, or soft-deleted | `404` | `project_not_found` |
| `name` empty/blank or > 255 chars | `422` | `validation_error` |
| `limit`/`offset` out of range | `422` | `validation_error` |

> **Ownership = existence.** A project owned by another user must be
> indistinguishable from a non-existent one: always `404`, never `403`. This is a
> hard requirement (acceptance criterion 7).

**Service/repository layer (`app/services/project_service.py` or
`app/repositories/project_repository.py` per spec 02/03 conventions):**

- `create_project(session, owner_id, name) -> Project`
- `list_projects(session, owner_id, limit, offset) -> tuple[list[Project], int]`
- `get_owned_project(session, owner_id, project_id) -> Project` — raises a domain
  `ProjectNotFound` (mapped to 404) when missing/deleted/not-owned. The single
  query filters by `id == project_id AND owner_id == owner_id AND deleted_at IS NULL`.
- `rename_project(session, owner_id, project_id, name) -> Project`
- `soft_delete_project(session, owner_id, project_id) -> None`

The router maps `ProjectNotFound` to the `404` envelope via the app's exception
handlers (spec 02). No raw SQLAlchemy exceptions leak to the client.

### 5.3 Frontend / UI

None in this spec. The dashboard UI is spec 16.

### 5.4 Real-time / jobs / external integrations

None. No ARQ jobs, no WebSocket, no LLM, no Tectonic.

### 5.5 Configuration

No new env vars. The default list `limit` (50) and max (100) live as constants in
the router/schema, not env. (If spec 02 established a settings object, expose
`PROJECTS_DEFAULT_PAGE_SIZE`/`PROJECTS_MAX_PAGE_SIZE` there with the same defaults;
otherwise keep them as module constants — do not add env vars gratuitously.)

## 6. Overleaf reference (study only — never copy)

> Read these in `../overleaf/` to understand the approach only. Inkstave's model
> is **relational and minimal** and differs deliberately: Overleaf embeds the
> file tree in the Project document; Inkstave keeps the tree separate (spec 12).

- `services/web/app/src/Features/Project/ProjectController.mjs` — how create/clone/
  delete endpoints are shaped and what they return. Learn the *operations*, not
  the Mongoose code.
- `services/web/app/src/Features/Project/ProjectCreationHandler.mjs` — what a new
  project is initialised with (owner, name, default root doc). Inkstave creates an
  empty project here; default content seeding is deferred.
- `services/web/app/src/Features/Project/ProjectGetter.mjs` — how projects are
  fetched and scoped to a user.
- `services/web/app/src/Features/Project/ProjectDeleter.mjs` — Overleaf's
  soft-delete / "deleted projects" approach (tombstones). Informs our `deleted_at`.
- `services/web/app/src/Features/Project/ProjectDetailsHandler.mjs` — rename and
  name validation behaviour.

## 7. Acceptance criteria

1. **Given** a signed-in user, **when** they `POST /api/v1/projects` with
   `{"name": "My Paper"}`, **then** they get `201` and a `ProjectRead` whose
   `owner_id` is their id, `name` is `"My Paper"`, `root_doc_id` is `null`, and
   `id`/`created_at`/`updated_at` are populated.
2. **Given** a user with two projects, **when** they `GET /api/v1/projects`,
   **then** they receive both, newest-`updated_at` first, with `total == 2`, and
   **no** `deleted_at` field appears in any item.
3. **Given** a name `"   "` (only whitespace), **when** they create or rename,
   **then** they get `422 validation_error` and nothing is persisted/changed.
4. **Given** a project, **when** the owner `PATCH`es a new name, **then** `200`
   with the new (trimmed) name and an `updated_at` strictly greater than before.
5. **Given** a project, **when** the owner `DELETE`s it, **then** `204`, and a
   subsequent `GET`/`PATCH`/`DELETE` of that id returns `404 project_not_found`,
   and it no longer appears in the list.
6. **Given** no/invalid token, **when** any endpoint is called, **then** `401
   unauthorized` and no DB row is read or written.
7. **Given** user A's project id, **when** user B calls `GET`/`PATCH`/`DELETE` on
   it, **then** `404 project_not_found` (never `403`, never the project body) —
   existence is not leaked.
8. **Given** `limit=200`, **when** listing, **then** `422 validation_error`
   (max page size enforced).
9. The Alembic migration applies and rolls back cleanly on an empty DB, creating
   `projects` with the FK, check constraint and all three indexes (verified by
   inspecting the migrated schema).
10. The new tests run as part of the suite and the **whole** suite completes in
    under 2 minutes.

## 8. Test plan

> All tests combined must keep the suite under 2 minutes. Nothing here is slow;
> use the fast in-process async client + transactional test DB from spec 04.

- **Unit (pytest):**
  - Schema validation: `ProjectCreate`/`ProjectRename` trim and reject blank/oversized names.
  - Service functions with a session: create sets owner; `get_owned_project`
    raises `ProjectNotFound` for missing/deleted/other-owner ids; soft delete sets
    `deleted_at`; list excludes deleted and orders correctly.
- **Integration (pytest + httpx against the app + test Postgres):**
  - Full CRUD happy path (create → list → get → rename → delete → 404).
  - Ownership isolation: two users; each sees only their own; cross-access → 404
    for get/patch/delete (criterion 7).
  - Auth: every endpoint returns 401 without a token.
  - Pagination: `limit`/`offset` behaviour and `total` correctness; `limit` bounds
    enforced (422).
  - Validation: blank name 422; bad UUID path param 422.
  - Migration smoke: alembic upgrade head then downgrade base on the test DB
    (can reuse spec 03/04's migration test harness).
- **E2E (Playwright):** none at this stage (no UI until spec 16).
- **Performance/budget note:** all DB tests run inside a rolled-back transaction
  per test; no network, no external services. Migration up/down test runs once.
  Expected added runtime: a few seconds.

## 9. Definition of Done

- [ ] All requirements in §5 implemented (model, schemas, service, router, migration).
- [ ] All acceptance criteria in §7 pass.
- [ ] All tests in §8 written and green.
- [ ] Full suite runs in < 2 minutes.
- [ ] Lint/format/type-check clean (`ruff`, `mypy`/`pyright`).
- [ ] ADR `docs/adr/0011-project-delete.md` records the soft-delete decision.
- [ ] No new env vars required (or, if added, documented in `.env.example`).
- [ ] No Overleaf code copied.
