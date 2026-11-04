# Known gaps

What Inkstave knowingly does not do yet, and why. Findings were read from the code on 2026-10-30; "read,
not run" marks anything that was not exercised. Resolving a gap removes its entry in the same commit.

The first section is the agreed list. The second collects defects found while writing `docs/system/`.
Those were not fixed, because the documentation pass changed no code.

## Agreed gaps

### Architecture

**Three import-linter exceptions, no domain events.** `backend/pyproject.toml` allows
`modules.collab.ws.components -> modules.history`, `modules.projects.routes.projects -> modules.collab` and
`modules.projects.routes.projects -> modules.compile`. *Why:* the exit for each is an event between
modules, and no domain-event mechanism exists yet. `backend/tests/unit/test_architecture.py` only lets the
count go down.

### Frontend standard

**`flushBeforeCompile` does nothing.** `EditorWorkspace` never assigns `flushRef`, so a compile or agent message
does not wait for pending edits to reach the server. *Why:* found while splitting the editor; a fix changes
the compile path and needs its own test.

**The agent's changes are reviewed in a dialog, not in the text.** The approved demo showed hunks in the editor,
decided one by one. `DiffReviewDialog` is still the only review surface. *Why:* it needs a CodeMirror decoration
layer and per-hunk apply, a change of its own after spec 107.

**Field metrics are not collected.** *Why:* `web-vitals` waits for real users.

**The landing animates paint.** `.ink-underline` transitions `background-size` and `transition-all`
animates `box-shadow`. *Why:* not yet reviewed; its loops are an accepted exception (spec 106).

### Compile sandbox

**`COMPILE_RUNNER=sandbox` is unproven and probably does not work as deployed.** All four doubts come from
reading the code; none was run. *Why open:* it needs a real gVisor host, and the compile image and compose
are outside this pass.

- `backend/src/inkstave/modules/compile/running/sandbox.py` runs the docker client with only `PATH` and
  `HOME`, so `DOCKER_HOST`, which `infra/README.md` tells operators to set, never reaches it.
- `backend/Dockerfile` installs no docker CLI. A missing binary ends the compile as `error`.
- The bind mounts pass worker-container paths to the daemon. With the daemon on the host, those paths do
  not exist there, and the daemon creates empty directories.
- The workdir is `0700` for uid 10001, while the container runs as uid 65534.

### Deployment

**The production image may ship without a Tectonic cache.** `docker-compose.prod.yml` builds without the host
network, so where the build bridge has no IPv6 route the warmup in `backend/Dockerfile` warns and continues, and
the first compiles download the bundle at runtime and may time out. *Why:* Compose refuses `build.network: host`
without the `network.host` entitlement, which Coolify does not pass. Look for the warning in the build log.

**No `docker-compose-coolify.yml` or `docs/deploy-coolify.md`.** *Why:* user decision, not yet.
`docker-compose.prod.yml` is the only production file, publishes no host port and has no migrate step.

**nginx does not proxy `/health`.** `infra/nginx/default.conf` proxies only `/api/` and `/ws/`, so `/health`,
`/ready`, `/readyz`, `/docs` and `/redoc` hit the SPA fallback and answer 200. `/healthz` is answered by nginx
itself. *Why:* nginx is left as is by user decision.

**`X-Forwarded-Proto` is overwritten with `$scheme`.** An outer TLS proxy's value is lost. Nothing in
`backend/src` reads the scheme today, so nothing breaks yet. *Why:* same decision.

**No uvicorn `--proxy-headers`.** No flag is set and `FORWARDED_ALLOW_IPS` is not configured, so uvicorn does
not trust nginx's forwarded headers. *Why:* Docker is left untouched for now.

### Sessions and proxy trust

**Open WebSockets and SSE streams survive session revocation.** The session check runs only at admission
(`_admit` in `backend/src/inkstave/modules/collab/ws/router.py`, `sse_user` in
`backend/src/inkstave/modules/auth/deps.py`). The same holds when a collaborator is removed or demoted:
`can_write` is fixed at join. *Why:* it needs a kick channel from the revoking request to every instance.

**Refresh-token reuse detection misses `sid`.** `_validate_refresh` in
`backend/src/inkstave/modules/auth/accounts/login.py` revokes the refresh family in Redis but does not call
`revoke_session`, so access tokens of that session live until their TTL. *Why:* not done in the session
revocation pass; the window is bounded by `ACCESS_TOKEN_TTL_SECONDS`.

**The first `X-Forwarded-For` entry is spoofable when `TRUST_PROXY_HEADERS` is on.** `client_ip` takes
`forwarded.split(",")[0]`, and nginx appends to the client's header, so a client can choose its IP and evade
per-IP limits. *Why:* the right entry depends on the number of proxies, which is not configured anywhere.

**`deactivate-user` has no reactivate.** Undoing it takes SQL (`docs/admin-guide.md`). *Why:* an operator
tool added for the lockout case only.

### Language

**Backend errors and e-mails are English-only.** `backend/src/inkstave/infra/mailer/templates.py` hard-codes
subjects and bodies, and no code in `backend/src` reads a locale. English server messages therefore appear in
the Portuguese interface. *Why:* the language lives only in the browser. Delivering it needs a stored user
preference, and invites to non-users have no recipient record at all.

### Frontend

**The spell-check menu has no arrow-key navigation.** Tab moves through its items, but the arrow keys do not. *Why:* it is a popover of buttons, not a full menu; a roving-focus menu is a follow-up of spec 113.

**Spell check on iOS does not open its menu on a long press.** iOS Safari sends no `contextmenu` event for a long press on text, so the suggestions are reachable only where the browser sends one. *Why:* the only workaround takes over every long press of the editor, and the native menu must stay for other words.

**Type narrowing is still manual.** 10 casts cover API data, and `apiClient<T>` is an unchecked cast at 72
call sites, with no type predicates. *Why:* OpenAPI types are generated, but not yet threaded through the
modules' own API files.

### Tests and supply chain

**`a viewer cannot edit or compile` fails in the `@full` tier.** `frontend/e2e/flows/full.spec.ts` expects no Compile
button for a viewer, while `compile_for_viewers` defaults to `true` and offers one (`docs/system/sharing.md`). *Why:*
choosing which side is right is a product decision; the tier is outside CI.

**`_diff_summary` has no dedicated test.** The fix clears `hunks` when they are not requested
(`backend/src/inkstave/modules/agent/routes.py`). No test asserts it or uses `?include=hunks`. *Why:* the fix
landed with the API-contract work without one.

**`scripts/audit.sh` is not in CI, with open advisories.** `pip-audit` reported 41 advisories in 12 packages
on 2026-10-30, including pyjwt and aiohttp, and `scripts/audit-allowlist.txt` has no entries. The script's
`set -e` also exits before `npm audit`, which has no npm lockfile to read. *Why:* it would fail CI until the
dependencies are upgraded, a separate change.

## Found while documenting

Not triaged. Each is detailed in the "Points of attention" of its domain file. Items marked (reproduced) were
run; the rest were read, not run.

### Data correctness

- `PUT` on document content strips surrounding whitespace, through `str_strip_whitespace=True` on
  `DocumentContentReplace` (reproduced).
- The debounced CRDT text flush cancels itself and never writes, so `documents.content` stays stale until the
  last client leaves or a forced flush runs (reproduced with a fake bridge).
- A document's seed is never captured by history, so diffs and restore go wrong for any document that had
  content when first opened (reproduced on replay).
- A failed history flush loses its buffer.
- Multiple backend replicas are unsafe for collaboration: the forwarder never applies updates to the receiving
  `YDocument`, and compaction then overwrites the snapshot with partial state.
- Offloaded history blobs and project blobs are orphaned on delete.

### Stuck work

- Compiles have no reaper. A job enqueued before commit, a dead worker or an ARQ timeout leaves a row `queued` or
  `running`, and coalescing then returns it forever.
- Agent runs: `_resolve_llm` and `precheck_run` run outside any `try`, so a missing API key or a Redis failure
  leaves the session `queued` and new messages get 409. A worker crash does the same.
- Zip imports enqueue before commit, with `max_tries=1`.
- E-mail retries never happen: ARQ retries only on `Retry`, so `max_tries=3` on `send_email_job` does nothing.

### Authorization and security

- Agent event and cancel routes accept any `run_id`, unbound to the session in the path.
- `list_projects` filters on `owner_id`, so shared projects never appear in a collaborator's list.
- `COMPILE_ALLOWED_FOR_VIEWERS` is ignored by the compile job and the compile SSE route.
- Password-reset links survive an e-mail change, and `complete_password_reset` ignores `is_active`.
- Deleting the last admin reopens the public `POST /api/setup/admin`.
- Rate limits are missing on `/me/change-email`, `DELETE /me`, the invite routes and `/api/setup/admin`.
- Only login stands down behind an untrusted proxy; `refresh`, `forgot_password` and `reset_password` share one
  counter across all users there.
- Pre-accept close codes (4401, 4403, 4404) reach browsers as HTTP 403 from uvicorn, so the provider keeps retrying
  (403 reproduced; the browser side inferred).
- `doctor` prints the full `DATABASE_URL`, password included.
- `?token=` on the collab WebSocket lands in nginx access logs.
- The console e-mail backend logs tokens at INFO, and `check-config` does not flag it in production. The raw invite
  token is stored in the notification's `accept_url`.
- nginx's `add_header` inheritance drops security headers on `index.html`, and the SPA has no CSP.

### Limits that do not hold

- `COMPILE_MAX_OUTPUT_BYTES` is never enforced, and `/out` has no disk cap in the sandbox.
- The daily compile quota counts requests, is a fixed window and fails open. Concurrency caps are count-then-insert
  with no lock.
- The effective document size limit is `MAX_REQUEST_BODY_BYTES` (1 MiB), not `MAX_DOCUMENT_BYTES` (2 MB).
- `AGENT_MAX_TOKENS_PER_RUN` and the per-run cost cap are unreachable with defaults, since the 1000000 soft cap stops
  first.
- `gzip.decompress` on SyncTeX data has no output bound.

### Settings with no effect

`LOG_JSON`, `OTEL_ENABLED` (no opentelemetry package), `COLLAB_WS_PING_INTERVAL_SECONDS`,
`COLLAB_WS_PONG_TIMEOUT_SECONDS`, `COLLAB_WS_SLOW_CLIENT_TIMEOUT_MS`, `HISTORY_COMPACT_INTERVAL_S`,
`NOTIFICATION_SWEEP_INTERVAL_S`, `AGENT_STREAM_TRANSPORT`, `AGENT_SECTION_EXTRA_COMMANDS`, `TEST_DB_TEMPLATE`,
`PUBLIC_HTTP_PORT`, and most of `infra/tectonic/packages.toml` at runtime. `COMPILE_SANDBOX_MEMORY_MB` is ignored
while `COMPILE_ADDRESS_SPACE_BYTES` has its default.

### Observability

- A 500 has `request_id: null` and no `X-Request-ID`, security or CORS headers (reproduced).
- The body-limit 413 uses `error.code` rather than the envelope (reproduced), and unknown-route 404 and 405 answer
  `{"detail": ...}`.
- Worker metrics are never scraped, and `inkstave_job_queue_depth` reads `arq:queue` while the queue is `compiles`.

### Unused code

`configure_logging` in `backend/src/inkstave/core/logging.py`, `RequestIdMiddleware`, `select_context` in the agent
turn, `set_status` and `apply_recorded` on agent diffs (applied diffs stay `proposed` and reappear on reload),
`ensure_snapshot`. `COLLAB_ENABLED` is always true in a real build, so REST autosave and its conflict dialog are
unreachable.
