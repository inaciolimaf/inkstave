# Inkstave — API Reference

The REST API is described by an **OpenAPI 3.1** schema generated from the FastAPI
app, so this page does not hand-list endpoints — it points at the live,
always-current sources.

## Viewing the live docs

When `DOCS_ENABLED=true` (the default outside production), the running backend
serves interactive docs:

- **Swagger UI** — `/docs`
- **ReDoc** — `/redoc`
- **Raw schema** — `/openapi.json`

A committed snapshot lives at [`api/openapi.json`](api/openapi.json) for offline
browsing and diffing.

## Regenerating the artifact

The snapshot is generated from the real app factory, so it can never drift from
the routes/models:

```bash
cd backend && uv run python scripts/export_openapi.py
```

A fast test (`backend/tests/unit/test_docs.py`) regenerates the schema in memory
and **fails the build if it differs** from the committed file — run the export and
commit `docs/api/openapi.json` whenever you change an endpoint or schema.

## Authentication

Most endpoints require a **JWT bearer** access token:

```
Authorization: Bearer <access_token>
```

Obtain a pair from `POST /api/v1/auth/login`; refresh with
`POST /api/v1/auth/refresh` (rotating refresh tokens). The collaboration
WebSocket and the SSE event streams authenticate via a `token`/`access_token`
query parameter instead of a header. The first-run setup endpoints under
`/api/setup` are unauthenticated but self-lock once an admin exists.

## Endpoint groups

The versioned API is mounted under `/api/v1`, grouped by area:

- **auth** — register, login, refresh, logout.
- **users** — current user profile.
- **projects** + **tree** + **documents** — projects, the file tree, document
  content.
- **files** — binary uploads/downloads.
- **compile** — trigger compiles, fetch status/PDF/log/problems, SSE events.
- **synctex** — forward/inverse source↔PDF mapping.
- **history** — version timeline, diff, restore, labels.
- **sharing** — members, invites, permissions.
- **agent** — sessions, messages, run events (SSE), proposed diffs.
- **notifications** — the notifications bell.
- **admin** — admin-only operations.

Root-level (not versioned): `/health`, `/readyz`, `/metrics`, `/api/setup/*`, and
the `/ws/collab/...` WebSocket.
