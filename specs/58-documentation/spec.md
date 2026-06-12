# Spec 58 — Project Documentation (requirements)

## 1. Summary

This spec delivers Inkstave's documentation set: a polished top-level
`README.md`, an **admin/operations guide**, a **user guide**, an **architecture
doc** (services + data-flow diagrams), an **API reference generated from the
FastAPI OpenAPI schema**, and a **CONTRIBUTING guide** that reiterates the
no-Overleaf-code originality rule. It defines exactly where each document lives
under `docs/` and how the generated artifacts stay current.

## 2. Context & dependencies

- **Depends on:** most prior specs (the features being documented), especially
  **56** (deploy/compose/nginx), **57** (CI, migrations, bootstrap, env vars),
  **21–27** (compilation), **28–35** (collaboration), **41–50** (AI agent),
  **51–52** (observability/security).
- **Unlocks:** **60** (release readiness audits doc completeness), and external
  users/operators/contributors.
- **Affected areas:** `docs/`, top-level `README.md`, `CONTRIBUTING.md`, a small
  tooling script to export the OpenAPI schema, and a CI check.

## 3. Goals

- A **polished top-level `README.md`**: what Inkstave is, feature highlights,
  screenshots placeholder, quickstart (clone → `.env` → compose up), stack table,
  links into `docs/`, license & originality note.
- An **admin/operations guide**: deployment (spec 56 compose), full env-var
  reference, first-run bootstrap (spec 57), scaling, backups/restore, LaTeX
  package management (`infra/tectonic/packages.toml`), logs/metrics/health,
  upgrade & migration procedure, troubleshooting.
- A **user guide**: signing up, creating projects, the editor, compiling to PDF,
  SyncTeX, version history, real-time collaboration & sharing, and using the AI
  agent (chat, tools, reviewing/applying diffs, safety).
- An **architecture doc**: service inventory, responsibilities, data-flow
  diagrams (request flow, compile flow, collab/CRDT flow, agent flow), the data
  model overview, and links to existing ADRs under `docs/`.
- An **API reference** generated from the FastAPI **OpenAPI** schema (not
  hand-maintained), with a script + CI check that it stays in sync.
- A **CONTRIBUTING guide** covering dev setup, spec-driven workflow, test/budget
  rules, coding conventions, and an emphatic restatement of the
  **no-Overleaf-code** rule.

## 4. Non-goals (explicitly out of scope)

- Building a hosted docs site / static-site generator pipeline (plain Markdown in
  `docs/` is sufficient; a generator may be noted as future work).
- Producing actual screenshots/marketing assets (use placeholders with alt text
  and a `docs/assets/` location).
- Changing product behavior to match docs (document reality; log gaps for spec
  60).
- Localizing docs (English only, per project rule).

## 5. Detailed requirements

### 5.1 Documentation layout (where each doc lives)

```
README.md                      # top-level, polished overview + quickstart (updated)
CONTRIBUTING.md                # contributor guide incl. no-Overleaf-code rule
docs/
├── README.md                  # docs index / table of contents (links to all below)
├── user-guide.md              # end-user guide
├── admin-guide.md             # operations/admin guide
├── architecture.md            # services, data flow, data model, diagram links
├── api-reference.md           # human intro + link to generated OpenAPI artifact
├── api/
│   └── openapi.json           # generated artifact (and/or openapi.yaml)
├── assets/                    # screenshots placeholders, diagram sources/exports
└── adr/                       # existing ADRs from prior specs (link, don't move
                               #   if they already live under docs/ — match reality)
```

If earlier specs placed ADRs directly under `docs/` (not `docs/adr/`), keep that
location and have the architecture doc link to them; do not relocate existing
files. The index `docs/README.md` must link to every document above.

### 5.2 Top-level `README.md`

Update (do not discard the existing originality framing) to include:
- One-paragraph product description + the existing feature bullets.
- A **Screenshots** section with placeholder image references under
  `docs/assets/` and descriptive alt text (e.g. editor, PDF preview, agent
  panel).
- **Quickstart**: prerequisites (Docker), `cp .env.example .env`, set
  `OPENROUTER_API_KEY`, `docker compose -f docker-compose.prod.yml up --build`
  (and the dev compose for local hacking), first-run admin bootstrap pointer
  (spec 57), and the URL to open.
- The stack table (already present) and a **Documentation** section linking to
  each `docs/` file.
- License & originality note (MIT; Overleaf is reference-only, AGPLv3, no code
  copied).

### 5.3 Admin / operations guide (`docs/admin-guide.md`)

Sections (at minimum):
1. **Deployment** — production compose (spec 56), services overview, the nginx
   proxy and exposed port, TLS hook point.
2. **Configuration / env-var reference** — a table of every variable from
   `.env.example` with: name, required?, default, description, which services use
   it. Must stay consistent with `.env.example` (the test checks coverage).
3. **First run** — migrations (spec 57), admin bootstrap (CLI + `/api/setup`),
   optional demo seed.
4. **Scaling** — per-service scaling notes (`docker compose up --scale
   worker=N`), statelessness assumptions, Redis as broker/pubsub.
5. **Backups & restore** — Postgres dump/restore, uploaded-files volume, what is
   safe to lose (caches, ephemeral compile dirs).
6. **LaTeX package management** — how `infra/tectonic/packages.toml` works, the
   minimal default set, how to add packages, rebuild/restart implications, cache
   volume behavior.
7. **Observability** — where logs go, the `/metrics` endpoint (and that it is
   blocked at the public proxy), health endpoints.
8. **Upgrades** — pull new images, run migrations (forward-only), restart order.
9. **Troubleshooting** — common failures (DB not migrated, missing secret crash,
   compile timeouts, WebSocket upgrade issues behind a proxy).

### 5.4 User guide (`docs/user-guide.md`)

Sections: account creation & login; projects (create/rename/delete, file tree,
uploads); the editor (CodeMirror, LaTeX syntax, autosave); compiling (compile
button, PDF preview, logs, error annotations, SyncTeX forward/inverse); version
history (timeline, diff, restore, labels); collaboration (sharing, roles
owner/editor/viewer, live cursors/presence); the **AI agent** (opening the chat
panel, what it can do — search project, locate sections, propose edits — that it
streams, that **nothing is applied without explicit approval**, reviewing diffs
hunk-by-hunk, rate/cost limits). Keep it task-oriented with short steps.

### 5.5 Architecture doc (`docs/architecture.md`)

- **Service inventory**: backend (API), worker (ARQ), collab/WS, frontend/nginx,
  Postgres, Redis, Tectonic — responsibilities and how they map to spec-56
  containers.
- **Data-flow diagrams** (at least these four), as Mermaid (preferred, renders on
  GitHub) and/or exported images under `docs/assets/`:
  1. **Request flow**: browser → nginx → API → Postgres/Redis.
  2. **Compile flow**: editor → compile API → ARQ job → Tectonic sandbox →
     output storage → PDF preview.
  3. **Collab flow**: browser Yjs ↔ WebSocket ↔ pycrdt ↔ persistence; presence.
  4. **Agent flow**: chat → LangGraph graph → tools → streamed tokens/diffs →
     user review/apply.
- **Data model overview**: the principal entities (users, projects, files/docs,
  versions, collaborators, agent sessions) and their relationships, at a level
  consistent with the migrations.
- Links to the per-spec ADRs.

### 5.6 API reference (generated, `docs/api-reference.md` + `docs/api/openapi.*`)

- A script `scripts/export_openapi.py` (or equivalent under the backend tooling)
  imports the FastAPI app and writes the OpenAPI schema to
  `docs/api/openapi.json` (and optionally `.yaml`).
- `docs/api-reference.md` is a short human page: how to view the live docs
  (`/docs` Swagger UI / `/redoc` if enabled per spec 02), how to regenerate the
  artifact, grouping of endpoints by area, and auth (JWT bearer) overview. It
  must **link** to the generated artifact rather than restating every endpoint by
  hand.
- A **CI check** (and a fast test) regenerates the schema in-memory and asserts it
  matches the committed `docs/api/openapi.json` (fail if drifted), so the
  reference cannot silently go stale.

### 5.7 CONTRIBUTING guide (`CONTRIBUTING.md`)

- Dev environment setup (`uv`, `pnpm`, dev compose), running the test suite, the
  **< 2-minute budget** rule, lint/format/type-check commands.
- The **spec-driven workflow** (implement `specs/` in order; refactor every 5th).
- Coding conventions (async-first backend, shadcn on frontend, migrations per
  schema change).
- A prominent **Originality / no-Overleaf-code** section restating: Overleaf is
  AGPLv3 reference material only; never copy/paste/translate; all code is MIT and
  independently written. Include how to declare a PR is original work.
- PR checklist (tests green, budget respected, docs updated, no Overleaf code).

### 5.8 Configuration

- No new runtime env vars. If a docs-export or link-check tool is added, document
  its invocation in `CONTRIBUTING.md` and wire it into CI (spec 57's pipeline).

## 6. Overleaf reference (study only — never copy)

> Structure/inspiration only. Do not copy Overleaf prose or code; write original
> Inkstave documentation. Verify paths before citing.

- `README.md` (repo root) — how a project README frames product + quickstart.
- `doc/` — Overleaf keeps minimal in-repo docs/assets (`logo.png`,
  `screenshot.png`); informs the screenshots-placeholder and assets approach.
- `CONTRIBUTING.md` — contributor-guide structure (setup, conventions, PR flow).
- The Overleaf wiki (external) — only as a mental model of user/admin topic
  coverage; nothing copied.

## 7. Acceptance criteria

1. **Given** the repo, **when** I open the top-level `README.md`, **then** it
   contains the product overview, a screenshots section (placeholders under
   `docs/assets/`), a working quickstart referencing the spec-56 compose and the
   spec-57 bootstrap, the stack table, a Documentation section linking to each
   `docs/` file, and the MIT/originality note.
2. **Given** `docs/admin-guide.md`, **when** I read it, **then** it covers deploy,
   a complete env-var reference table, first-run bootstrap, scaling, backups,
   LaTeX package management, observability, upgrades, and troubleshooting.
3. **Given** `.env.example`, **when** the test compares it to the admin guide's
   env-var table, **then** **every** variable in `.env.example` appears in the
   table (no undocumented vars).
4. **Given** `docs/user-guide.md`, **when** I read it, **then** it covers editing,
   compiling, SyncTeX, history, collaboration/sharing/roles, and the AI agent —
   including the explicit statement that the agent never applies changes without
   user approval.
5. **Given** `docs/architecture.md`, **when** I read it, **then** it lists the
   services, includes the four data-flow diagrams (request, compile, collab,
   agent) as Mermaid/images, an entity/data-model overview, and links to ADRs.
6. **Given** the backend, **when** I run `scripts/export_openapi.py`, **then** it
   writes `docs/api/openapi.json`; **and** a test regenerating the schema asserts
   it matches the committed artifact (drift fails).
7. **Given** `docs/api-reference.md`, **when** I read it, **then** it explains how
   to view live docs, how to regenerate the artifact, the auth model, and links to
   the generated file (rather than hand-listing endpoints).
8. **Given** `CONTRIBUTING.md`, **when** I read it, **then** it covers dev setup,
   the test budget, the spec-driven workflow, conventions, a PR checklist, and a
   prominent no-Overleaf-code originality section.
9. **Given** all docs, **when** the link-check test runs, **then** every relative
   link/anchor between docs resolves (no broken internal links).
10. **Given** `docs/README.md`, **when** I open it, **then** it links to every
    document in §5.1.

## 8. Test plan

> All tests are fast file/string checks plus an in-memory OpenAPI export — well
> within the budget.

- **Unit (pytest):**
  - **Doc presence/sections:** assert each required file exists and contains its
    required top-level section headings (parse Markdown headings).
  - **Env-var coverage:** parse variable names from `.env.example` and assert each
    appears in the admin guide's env table.
  - **Internal link check:** scan Markdown for relative links/anchors and assert
    targets exist (files + heading anchors).
  - **OpenAPI sync:** import the app, generate the OpenAPI dict, and assert it
    equals the committed `docs/api/openapi.json` (normalized); failing on drift.
  - **Originality clause:** assert `CONTRIBUTING.md` contains the no-Overleaf-code
    statement (keyword check).
- **Integration:** none required (docs are static); the OpenAPI test exercises the
  real app factory in-memory.
- **E2E (Playwright):** none.
- **Performance/budget note:** pure Markdown parsing + one in-memory app import;
  no containers, no network.

## 9. Definition of Done

- [ ] All requirements in §5 implemented (all docs present and complete).
- [ ] All acceptance criteria in §7 pass.
- [ ] All tests in §8 written and green (presence, env coverage, links, OpenAPI
      sync, originality clause).
- [ ] Full suite runs in < 2 minutes.
- [ ] `docs/api/openapi.json` committed and in sync; export script wired into CI.
- [ ] Lint/format clean (Markdown lint if configured; otherwise consistent style).
- [ ] No Overleaf documentation or code copied.
