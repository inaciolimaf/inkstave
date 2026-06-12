# Release Checklist (spec 60)

An ordered, actionable checklist to cut an Inkstave release from a clean checkout.
Each step is verifiable; the parenthetical command is the quickest way to confirm
it. See the [Admin Guide](admin-guide.md) for production operations detail.

## 1. Quality gates (local or CI)

- [ ] **Tests green & under 2 minutes.** Unit + integration + e2e.
      `cd backend && uv run pytest -n auto` (836 passed, 1 skipped, ~18 s);
      `cd frontend && pnpm test` (326 passed); e2e
      `pnpm exec playwright test --project=smoke` (~23 s). Combined ≈ 55 s < 120 s —
      the CI `budget` job enforces this automatically.
- [ ] **Lint/format clean.** `cd backend && uv run ruff check . && uv run ruff format --check .`;
      `cd frontend && pnpm lint && pnpm format:check`.
- [ ] **Type-check clean.** `uv run mypy src` (baseline tolerated) and
      `pnpm typecheck`.
- [ ] **Docs & OpenAPI in sync.** `cd backend && uv run pytest tests/unit/test_docs.py`
      (links resolve, every `.env.example` var documented, `docs/api/openapi.json`
      matches the live schema). Regenerate with `uv run python scripts/export_openapi.py`
      if it drifted.
- [ ] **Originality audit passed.** See [originality-audit.md](originality-audit.md)
      (MIT license, no Overleaf code) — re-run its grep checks if the tree changed.
- [ ] **Dependency advisories triaged.** `cd frontend && pnpm audit --prod`;
      backend `uvx pip-audit -r <(uv pip freeze)`. Both clean at this release.

## 2. Images build within size targets (spec 56)

- [ ] `docker build -f backend/Dockerfile -t inkstave-backend .` and
      `docker build -f frontend/Dockerfile -t inkstave-frontend .` succeed.
- [ ] Both run as **non-root**, bake **no secrets**, and stay within the soft size
      gates (frontend ≤ 80 MB, backend ≤ 450 MB). The CD workflow checks this.
- [ ] **Prerequisite:** `frontend/pnpm-lock.yaml` is committed (the CI/CD frontend
      jobs use `--frozen-lockfile`; see [adr/0056-docker-production.md](adr/0056-docker-production.md)).

## 3. Configuration

- [ ] `cp .env.example .env`; set a strong `JWT_SECRET` (≥ 32 bytes),
      `CORS_ORIGINS` (your public origin), `OPENROUTER_API_KEY`, and
      `ENVIRONMENT=prod`.
- [ ] **Env validation fails fast on missing secrets:**
      `docker compose -f docker-compose.prod.yml run --rm backend python -m inkstave.cli check-config`
      exits 0 only when the config is valid.

## 4. Bring up & migrate (spec 57)

- [ ] `docker compose -f docker-compose.prod.yml up -d --wait` — all services
      report **healthy** (Postgres, Redis, backend, worker, frontend).
- [ ] **Migrations applied:**
      `docker compose -f docker-compose.prod.yml run --rm backend python -m inkstave.cli migrate`
      (advisory-locked, idempotent, forward-only). In strict mode the app refuses to
      start unless the DB is at head.

## 5. First-run bootstrap (spec 57)

- [ ] **Admin created on a fresh DB** (idempotent):
      `... run --rm -e INKSTAVE_ADMIN_EMAIL=you@example.com -e INKSTAVE_ADMIN_PASSWORD=… backend python -m inkstave.cli bootstrap-admin`,
      or `POST /api/setup/admin` (locks after the first admin).
- [ ] `GET /api/setup/status` reports `{"needs_setup": false}` afterwards.

## 6. Smoke the key user flow

- [ ] Open the published URL (`PUBLIC_HTTP_PORT`); sign in as the admin.
- [ ] Create a project, edit `main.tex`, **compile to PDF**, view the preview.
- [ ] Open the **AI agent** panel, request an edit, confirm it appears as a
      reviewable diff and is **not** applied without approval.
- [ ] `just agent-live` passes with a real `OPENROUTER_API_KEY` (run **locally,
      never in CI** — it makes one real OpenRouter call; skips cleanly without a key).
- [ ] `/metrics` is **blocked** at the public proxy (returns 404); `/healthz` is OK.

## 7. Tag the release

- [ ] Update `docs/CHANGELOG.md`; commit.
- [ ] Tag (`git tag vX.Y.Z`) — the CD workflow builds, smokes, and (if registry
      credentials are configured) publishes the images.
