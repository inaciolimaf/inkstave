# Inkstave — Specification Roadmap

This folder is the **source of truth** for what to build and in what order.
Implement specs **strictly in numerical order**: finish `01` (code + passing
tests) before starting `02`, and so on. Each later spec assumes every earlier
spec exists and works.

## How each spec folder is structured

```
specs/NN-slug/
├── README.md     # the PROMPT for the implementing agent: goal, dependencies,
│                 # Overleaf references to study, and "requirements are in spec.md"
└── spec.md       # the detailed requirements: scope, data model, API/UI
                  # contracts, acceptance criteria, and the test plan
```

See [`_TEMPLATE/`](_TEMPLATE/) for the canonical structure all specs follow.

## Rules that apply to every spec

- **No Overleaf code is ever copied.** Overleaf (AGPLv3) is read only to
  understand approaches; Inkstave (MIT) is written independently. See `CLAUDE.md`.
- **Full test suite stays under 2 minutes.** Slow work → async ARQ jobs, mocked
  in tests.
- **A spec is done** only when its Definition of Done and Acceptance criteria
  pass, tests included.

## Refactoring cadence

Every 5th spec (**05, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60**) is a
**refactoring spec**: no new features. Agents scan everything built so far for
bugs and bad practices, judge whether each fix is worth applying, and apply the
worthwhile ones while keeping tests green.

## The roadmap

Legend: 🟢 feature · 🔧 refactor

### Phase 0 — Foundations
| # | Spec | Type |
| --- | --- | --- |
| 01 | `01-project-scaffolding` — monorepo layout, tooling, base docker-compose, .env | 🟢 |
| 02 | `02-backend-foundation` — FastAPI app, settings, logging, error handling, health | 🟢 |
| 03 | `03-database-foundation` — Postgres, async SQLAlchemy, Alembic, base models | 🟢 |
| 04 | `04-testing-foundation` — pytest/Vitest/Playwright setup, fixtures, 2-min budget, CI | 🟢 |
| 05 | `05-refactor-foundations` — refactor pass over the foundations | 🔧 |

### Phase 1 — Auth & users
| # | Spec | Type |
| --- | --- | --- |
| 06 | `06-user-model-registration` — user model, signup, password hashing | 🟢 |
| 07 | `07-jwt-authentication` — login, access + refresh tokens, rotation | 🟢 |
| 08 | `08-auth-guards-sessions` — current-user dependency, protected routes, logout | 🟢 |
| 09 | `09-frontend-foundation` — Vite/React/TS/Tailwind/shadcn, routing, API client, auth pages | 🟢 |
| 10 | `10-refactor-auth` — refactor pass over auth & frontend foundation | 🔧 |

### Phase 2 — Projects & files
| # | Spec | Type |
| --- | --- | --- |
| 11 | `11-project-model-crud` — project entity & CRUD API | 🟢 |
| 12 | `12-file-tree-model` — folders/docs/files tree, paths, moves | 🟢 |
| 13 | `13-document-content-api` — document content storage & CRUD | 🟢 |
| 14 | `14-binary-file-storage` — uploads & storage abstraction (disk / S3-compatible) | 🟢 |
| 15 | `15-refactor-projects` — refactor pass over projects & files | 🔧 |
| 16 | `16-project-dashboard-ui` — project list/create/rename/delete UI | 🟢 |
| 17 | `17-file-tree-ui` — file tree UI with drag-and-drop | 🟢 |
| 18 | `18-editor-ui-codemirror` — CodeMirror 6 editor, LaTeX syntax, open docs | 🟢 |
| 19 | `19-document-autosave-rest` — single-user autosave & REST sync | 🟢 |
| 20 | `20-refactor-editor` — refactor pass over editor & file-tree UI | 🔧 |

### Phase 3 — Compilation
| # | Spec | Type |
| --- | --- | --- |
| 21 | `21-tectonic-integration` — Tectonic compile service, sandbox, editable package config | 🟢 |
| 22 | `22-compile-api-async-jobs` — compile API + ARQ job + status streaming | 🟢 |
| 23 | `23-output-storage` — PDF/log/synctex output storage & retrieval | 🟢 |
| 24 | `24-pdf-preview-ui` — PDF.js preview, compile button, log panel | 🟢 |
| 25 | `25-refactor-compilation` — refactor pass over compilation | 🔧 |
| 26 | `26-synctex` — forward/inverse SyncTeX source↔PDF sync | 🟢 |
| 27 | `27-compile-error-annotations` — parse logs, inline editor annotations | 🟢 |

### Phase 4 — Real-time collaboration
| # | Spec | Type |
| --- | --- | --- |
| 28 | `28-crdt-backend-pycrdt` — pycrdt document model, Yjs protocol, persistence | 🟢 |
| 29 | `29-collab-websocket` — JWT-authed WebSocket, rooms, presence plumbing | 🟢 |
| 30 | `30-refactor-realtime-core` — refactor pass over CRDT backend & WS | 🔧 |
| 31 | `31-frontend-yjs-binding` — y-codemirror.next binding, live sync | 🟢 |
| 32 | `32-presence-awareness-ui` — collaborator cursors, selections, online list | 🟢 |
| 33 | `33-collaborators-sharing` — invites & roles (owner/editor/viewer) | 🟢 |
| 34 | `34-access-control` — authz enforcement across REST, WS and compile | 🟢 |
| 35 | `35-refactor-collaboration` — refactor pass over collaboration | 🔧 |

### Phase 5 — Version history
| # | Spec | Type |
| --- | --- | --- |
| 36 | `36-history-capture` — capture snapshots/updates from CRDT, storage model | 🟢 |
| 37 | `37-history-api` — list versions, diff, labels | 🟢 |
| 38 | `38-history-ui` — timeline, diff viewer, restore | 🟢 |
| 39 | `39-notifications-email` — invite emails & in-app notifications (async via ARQ) | 🟢 |
| 40 | `40-refactor-history` — refactor pass over history & notifications | 🔧 |

### Phase 6 — AI writing agent
| # | Spec | Type |
| --- | --- | --- |
| 41 | `41-agent-foundation` — LangGraph graph, OpenRouter-via-DI LLM client, config | 🟢 |
| 42 | `42-agent-tools` — tools: search project, read file, locate section, propose edit | 🟢 |
| 43 | `43-agent-diff-generation` — per-file unified diffs, never auto-applied | 🟢 |
| 44 | `44-agent-api-streaming` — streaming chat sessions, ARQ orchestration | 🟢 |
| 45 | `45-refactor-agent-core` — refactor pass over the agent core | 🔧 |
| 46 | `46-agent-chat-ui` — browser chat panel, streamed tokens & tool calls | 🟢 |
| 47 | `47-diff-review-ui` — diff viewer, accept/reject per hunk, apply to docs | 🟢 |
| 48 | `48-agent-context-section-parsing` — project awareness, LaTeX section locator | 🟢 |
| 49 | `49-agent-safety-evals` — rate limits, cost controls, eval test suite | 🟢 |
| 50 | `50-refactor-agent` — refactor pass over the full agent feature | 🔧 |

### Phase 7 — Hardening, packaging & docs
| # | Spec | Type |
| --- | --- | --- |
| 51 | `51-observability` — structured logging, metrics, tracing | 🟢 |
| 52 | `52-security-hardening` — rate limiting, validation, CORS, secrets, headers | 🟢 |
| 53 | `53-performance-test-speed` — keep suite < 2 min, parallelization, caching | 🟢 |
| 54 | `54-e2e-suite` — Playwright covering auth→project→compile→collab→agent | 🟢 |
| 55 | `55-refactor-hardening` — refactor pass over hardening | 🔧 |
| 56 | `56-docker-production` — Alpine multi-stage images, compose, nginx | 🟢 |
| 57 | `57-ci-cd-bootstrap` — CI/CD, migrations on deploy, admin bootstrap, seeds | 🟢 |
| 58 | `58-documentation` — user & admin docs, API reference | 🟢 |
| 59 | `59-user-settings-profile` — preferences, profile, account management | 🟢 |
| 60 | `60-refactor-final` — final refactor & release-readiness pass | 🔧 |

### Phase 8 — Runtime & validated fix-packs
Specs 61–90 (`runtime-*` and `fixpack-*`) extend the roadmap with runtime-error
surfaces and a series of disjoint, parallel-applicable fix-packs closing
two-reviewer-validated issues across specs 01–59. See each folder's `README.md`.

### Phase 9 — Code-smell audit fix-packs
Each closes one cluster of findings from a 15-dimension code-smell audit
(magic numbers, missing logging, blocking the event loop, DRY, etc.). Unlike the
68–90 packs these are **sequential**, not disjoint: where two packs touch the
same file the later one declares a prerequisite on the earlier (e.g. 93 after 92,
94 after 92/93, 96 after 94, 99 after 95).

| # | Spec | Type |
| --- | --- | --- |
| 91 | `91-fixpack-secret-hygiene` — rotate exposed key, pre-commit secret/`.env` guard | 🔧 |
| 92 | `92-fixpack-auth-logging` — log auth security events; stop swallowing WS-auth errors | 🔧 |
| 93 | `93-fixpack-async-offload` — Argon2/SHA-256/file-I/O off the event loop via `to_thread` | 🔧 |
| 94 | `94-fixpack-clock-injection` — injectable `Clock` for testable token/expiry logic | 🔧 |
| 95 | `95-fixpack-tree-entity-dry` — one shared TreeEntity-fetch helper; drop dead re-export | 🔧 |
| 96 | `96-fixpack-keyword-only-signatures` — keyword-only params; split control-couple flag | 🔧 |
| 97 | `97-fixpack-magic-numbers` — name budget TTL & section-locate score constants | 🔧 |
| 98 | `98-fixpack-pydantic-defaults` — `Field(default_factory=...)` for mutable settings defaults | 🔧 |
| 99 | `99-fixpack-query-efficiency` — kill a file-read N+1; bound unbounded tree fetches | 🔧 |
| 100 | `100-fixpack-schema-validation` — fail-fast `Field`/`Literal` constraints on two schemas | 🔧 |

**Core roadmap: 60 specs (48 feature 🟢 + 12 refactor 🔧), extended by fix-packs 61–100.**

> The roadmap can be extended later (the user may add requirements). New specs
> continue the numbering and keep the every-5th refactor cadence.
