# ADR 0058 — Documentation set & generated API reference

**Status:** accepted (spec 58) · **Phase:** 7 — Hardening, packaging & docs

## Context

Inkstave needs navigable docs for users, operators and contributors, kept honest
by tests rather than manual upkeep.

## Layout (where each document lives)

```
README.md            # polished product overview + quickstart
CONTRIBUTING.md      # dev setup, test budget, spec-driven workflow, originality rule
docs/
├── README.md         # docs index (links to everything)
├── user-guide.md     # end-user features
├── admin-guide.md    # deploy/ops + the full env-var reference table
├── architecture.md   # services + 4 Mermaid data-flow diagrams + data model + ADR links
├── api-reference.md  # how to view live docs + how to regenerate the schema
├── api/openapi.json  # generated OpenAPI 3.1 artifact (committed)
├── assets/           # screenshot placeholders + the assets README
├── adr/              # per-spec ADRs (this file lives here)
└── refactors/        # refactor-pass logs
```

Existing ADRs and refactor logs were **not relocated**; the architecture doc links
to them in place.

## Decisions

- **Plain Markdown, no docs-site toolchain.** GitHub renders it (Mermaid included);
  a static-site generator is noted as future work, not built (spec 58 non-goal).
- **API reference is generated, never hand-listed.** `scripts/export_openapi.py`
  writes `docs/api/openapi.json` from the real app factory (the schema is
  env-independent — title/version are static). A fast test
  (`tests/unit/test_docs.py::test_openapi_artifact_in_sync`) regenerates it in
  memory and fails the build on drift, so it runs as the CI check inside the unit
  stage (spec 57 pipeline). `api-reference.md` only links to the artifact and the
  live `/docs` UI.
- **The admin-guide env-var table is generated from `.env.example`** so it covers
  every variable; a test (`test_admin_guide_documents_every_env_var`) enforces it,
  catching any future undocumented var.
- **Doc integrity is tested**: required files + section headings, internal
  link/anchor resolution, the originality clause, and OpenAPI sync — all fast,
  in-budget file checks.

## Regenerating

- API schema: `cd backend && uv run python scripts/export_openapi.py` then commit
  `docs/api/openapi.json`.
- Env table: rebuild from `.env.example` if it changes (the coverage test flags
  drift).
