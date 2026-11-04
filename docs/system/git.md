# Git access

Clone, pull and push a project with Git over Smart HTTP. The server keeps one bare repository per project,
with one branch, `main`, and runs dulwich (pure Python, so the images need no `git` binary). A fetch first
commits the live project to `main`, so a clone always holds what the editors see. A push is accepted only as a
fast-forward of that state, and its changes become ordinary edits: tree operations for files, minimal CRDT
edits for text. Personal access tokens authenticate the client. Spec 121; the decision is
[ADR 0121](../adr/0121-git-access-dulwich-snapshot-sync.md). The module is `backend/src/inkstave/modules/git`.

## Where it is

| File | Role |
|---|---|
| `backend/src/inkstave/modules/git/__init__.py` | Exports `GitAccessToken`, `GitRepoState` |
| `backend/src/inkstave/modules/git/routes/smart_http.py` | The four Smart HTTP routes (HTTP only) |
| `backend/src/inkstave/modules/git/routes/tokens.py` | Token routes, under the session JWT |
| `backend/src/inkstave/modules/git/service.py` | `advertise_refs`, `upload_pack`, `receive_pack`: the order of effects |
| `backend/src/inkstave/modules/git/lock.py` | `project_git_lock`: the Redis lock per project |
| `backend/src/inkstave/modules/git/models.py` | `GitAccessToken`, `GitRepoState` |
| `backend/src/inkstave/modules/git/auth/` | Package: `access.py` (`authorize_git`, the Git gate), `tokens.py` (token format, storage, `authenticate`) |
| `backend/src/inkstave/modules/git/repo/` | Package: `repository.py` (bare repos, `snapshot_commit`), `snapshot.py` (`snapshot_locked`), `protocol.py` (dulwich's handlers, command parsing) |
| `backend/src/inkstave/modules/git/push/` | Package: `receive.py` (`prepare_push`), `changes.py` (rename detection, validation), `apply.py` (tree operations), `live.py` (CRDT edits), `textmerge.py` (the merge) |
| `backend/src/inkstave/modules/git/schemas.py` | Token request and response models |
| `backend/src/inkstave/modules/git/errors.py` | `GitDisabledError`, `GitUnauthorizedError`, body and media errors |
| `backend/src/inkstave/modules/admin/routes/public_config.py` | `GET /api/v1/config`: `git_enabled` for the UI |
| `backend/src/inkstave/core/http/body_limit.py` | Exempts `git-receive-pack` and sets its own cap |
| `frontend/src/modules/settings/GitAccessSection.tsx` | Settings → "Git access tokens" |
| `frontend/src/modules/settings/git-api.ts` | Token API calls |
| `frontend/src/modules/editor/git-clone-dialog.tsx` | Editor → More → "Git": the clone address and command |
| `frontend/src/modules/editor/git-url.ts` | `gitCloneUrl` |
| `frontend/src/lib/public-config.ts` | `usePublicConfig`, read once per session |
| `backend/tests/unit/test_git_repository.py` | Snapshot, lost directory, renames, ancestry |
| `backend/tests/unit/test_git_validation.py` | Pre-receive rules, token parsing and hashing |
| `backend/tests/unit/test_git_textmerge.py` | The minimal-edit merge, including UTF-8 offsets |
| `backend/tests/integration/_git_support.py` | dulwich's HTTP client driven into the ASGI app |
| `backend/tests/integration/test_git_smart_http.py` | Clone, roles, 401 and 404, disabled, dumb protocol |
| `backend/tests/integration/test_git_push.py` | Push rules, CRDT path, rename, lock, conflicts |
| `backend/tests/integration/test_git_tokens_api.py` | Token API, limit, expiry, rate limit |
| `frontend/src/modules/settings/GitAccessSection.test.tsx` | Settings section |
| `frontend/src/modules/editor/editor-bar.git.test.tsx` | The menu item, on and off |

## Data

Migrations: `backend/migrations/versions/20261104_1000_e7a1c3d5b9f2_create_git_access.py` (both tables) and
`backend/migrations/versions/20261104_1100_f2b4d6e8a0c1_history_update_origin.py` (`history_updates.origin`).

| Table | Key columns | Constraints |
|---|---|---|
| `git_access_tokens` | `user_id`, `name`, `token_hash`, `prefix`, `created_at`, `last_used_at`, `expires_at`, `revoked_at` | `uq_git_access_tokens_token_hash`; `ix_git_access_tokens_user_id`; `name` 1–100 characters; `user_id` cascades |
| `git_repo_state` | `project_id`, `head`, `updated_at` | One row per project; `project_id` cascades. `head` is the commit `main` pointed to after the last snapshot or push |
| `history_updates.origin` | nullable text | `NULL` for an editor's change; `git-push` for a push |

Only the SHA-256 of a token is stored (`hash_token`, the same function the auth module uses). The raw token
is returned once, by the creation response.

On disk: `{GIT_REPOS_ROOT}/{project_id}.git`, one bare repository per project, HEAD symbolic to
`refs/heads/main`. It is derived data: a missing directory is recreated from the project as a single commit.

## Routes

Smart HTTP paths are under `/api/v1/git/projects/{project_id}.git`. The client's user name is ignored and
the password is the token (HTTP Basic). Errors use the error envelope; the 401 also carries
`WWW-Authenticate: Basic realm="Inkstave"`, so Git asks for the password.

| Method and path | Access | What it does | Errors |
|---|---|---|---|
| GET `/info/refs?service=git-upload-pack` | token, `DOC_READ` | Snapshot, then advertise `main` for fetch | 401 `unauthorized`, 404 `project_not_found`, 404 `not_found` (no smart `service`), 409 `git_busy`, 429 `rate_limited` |
| POST `/git-upload-pack` | token, `DOC_READ` | Negotiate and send the pack | 401, 404, 409 `git_busy`, 413 `payload_too_large`, 415 `unsupported_media_type`, 400 `git_protocol` |
| GET `/info/refs?service=git-receive-pack` | token, `DOC_WRITE` and `FILE_WRITE` | Snapshot, then advertise `main` for push | 401, 403 `insufficient_role`, 404, 409 `git_busy` |
| POST `/git-receive-pack` | token, `DOC_WRITE` and `FILE_WRITE` | Apply a push, or refuse it whole in the report (refusals are reported in the pack protocol, HTTP 200) | 401, 403, 404, 409 `git_busy`, 413 (over `GIT_MAX_PUSH_BYTES`), 415 |

Token routes take the session JWT, not a Git token. A Git token on them is a 401.

| Method and path | What it does | Errors |
|---|---|---|
| POST `/api/v1/git/tokens` | Create `{name, expires_at?}`; 201 with the raw `token` once | 409 `token_limit` (20 active), 422 |
| GET `/api/v1/git/tokens` | Usable tokens of the caller, newest first: name, prefix, dates | |
| DELETE `/api/v1/git/tokens/{token_id}` | Revoke; 204 | 404 `token_not_found` |
| GET `/api/v1/config` | `{git_enabled}`, public, no login | |

Every route answers 404 `not_found` when `GIT_ENABLED` is off, as if it did not exist. The dumb protocol is not
served: `info/refs` without a smart `service` is a 404.

## How it works

**Snapshot** (`service._snapshot` → `snapshot.snapshot_locked`). Every `info/refs` (either service) and every
push runs it first, under the project lock: open CRDT rooms are flushed (`flush_open_project_docs`), the tree is
read from `tree_entities`, `documents.content` and the blob store (`read_project_files`), and
`repository.snapshot_commit` commits it to `main` only when the tree differs. The commit is authored
"Inkstave <noreply@inkstave>" with the message "Update from Inkstave". `git_repo_state.head` is then recorded.

**Fetch.** `upload_pack` runs dulwich's `UploadPackHandler` on the repository in a thread, under the lock and the
deadline. The response is streamed in chunks; dulwich builds the pack in memory first.

**Push** (`service.receive_pack`), in this order:

1. Take the project lock and snapshot, so `main` is the current state.
2. `receive.prepare_push` in a thread: parse the commands; ingest the thin pack capped at `GIT_MAX_PUSH_BYTES`;
   refuse any ref but `refs/heads/main` and any deletion; require the pushed commit to descend from `main`
   (`PULL_FIRST` otherwise); diff old → new with `changes.collect_changes`; run `changes.validate_changes`.
   Any problem refuses the push, with one message per path, and nothing is written.
3. `apply.apply_changes` in one session transaction, through the projects services (`create_entity`,
   `rename_entity`, `move_entity`, `upload_file`, `ensure_root`), so names and sibling rules are the web app's.
   New blobs are written before the commit and deleted if it fails; replaced blobs are deleted after it.
4. `live.apply_live_texts` for each changed document: `textmerge.plan_text_edits` maps the push's hunks onto the
   live text, `DocumentManager.apply_server_edits` applies them as minimal edits with origin `git-push`, the
   history is flushed, the update is captured with the pusher as author and origin `git-push`, and the update is
   published to the room. Conflicting regions are reported as warnings.
5. `_move_main` moves `main` to the pushed commit, records `git_repo_state.head`, and logs the push.
6. The report-status (with the warnings on side-band 2) goes back to the client.

**Merge rule** (`textmerge`). The push is the diff `old → new`, where `old` is the previous `main` text. Each
hunk is mapped into the live text through the alignment of `old` and the live text. A hunk over lines that
collaborators changed is still applied, replacing that region, and reported as "lines N–M were also edited in
Inkstave; the pushed version was kept". The fast-forward check comes first, so a push built on an older snapshot
never reaches the merge.

**Authorization** (`access.authorize_git`): the feature flag, then the Git failure throttle, then the token
(`tokens.authenticate`: hash lookup, not revoked, not expired, account active; it stamps `last_used_at`), then the
member's role (`role_for`) against the capability set. No membership is 404; a missing capability is 403.
A failed token attempt counts against `RATE_LIMIT_GIT_AUTH` for the client IP, and a blocked IP gets 429.

**Lock** (`lock.project_git_lock`): `SET NX PX` with the operation's deadline as its expiry; waiters poll every 50 ms
until the deadline, then get 409 `git_busy`. The release deletes the key only when it still holds this holder's
token.

## Rules and guarantees

| Rule | Guarantee |
|---|---|
| A push is all or nothing | `backend/tests/integration/test_git_push.py::test_invalid_push_changes_nothing`, `::test_a_traversal_name_refuses_the_whole_push`, `::test_a_push_larger_than_the_cap_is_refused` |
| A push never silently overwrites unpulled web edits | `backend/tests/integration/test_git_push.py::test_non_fast_forward_refused`; `::test_after_a_pull_the_same_change_is_accepted` |
| Pushed text arrives as minimal live edits, and the history records the pusher | `backend/tests/integration/test_git_push.py::test_push_applies_through_crdt` |
| Collaborators' lines survive a push | `backend/tests/unit/test_git_textmerge.py::test_collaborator_lines_above_the_hunk_survive`, `::test_collaborator_edit_in_another_region_survives` |
| An overlapping hunk is applied and reported | `backend/tests/integration/test_git_push.py::test_a_conflicting_region_is_replaced_and_reported` |
| A rename keeps the entity | `backend/tests/integration/test_git_push.py::test_a_rename_keeps_the_entity_identity` |
| Two fetches with no change make one commit | `backend/tests/unit/test_git_repository.py::test_a_repeated_snapshot_of_an_unchanged_project_adds_no_commit`, `backend/tests/integration/test_git_push.py::test_the_next_fetch_after_a_push_adds_no_commit` |
| A lost repository is recreated as one commit | `backend/tests/unit/test_git_repository.py::test_the_lost_directory_is_recreated_as_a_single_commit` |
| One project's Git operations never interleave | `backend/tests/integration/test_git_push.py::test_a_second_push_waits_for_the_first_on_the_same_project`, `::test_a_waiter_gives_up_at_its_deadline` |
| A viewer clones and cannot push; a stranger gets 404; a revoked token gets 401 | `backend/tests/integration/test_git_smart_http.py::test_viewer_can_clone_but_not_push`, `::test_a_stranger_gets_404_and_no_token_gets_401_with_a_basic_challenge`, `::test_a_revoked_token_gets_401` |
| Tokens are stored as hashes and work only on Git routes | `backend/tests/integration/test_git_tokens_api.py::test_git_token_hash_only`, `backend/tests/integration/test_git_smart_http.py::test_git_token_rejected_on_api`, `::test_a_session_jwt_is_not_accepted_on_git_routes` |
| Token failures are rate limited per IP | `backend/tests/integration/test_git_tokens_api.py::test_repeated_failed_attempts_are_rate_limited_per_ip` |
| Git is off unless enabled | `backend/tests/integration/test_git_smart_http.py::test_git_disabled_404`, `::test_the_flag_is_on_when_git_is_enabled` |
| The Git routes are in the guard audit | `backend/tests/integration/test_authz_guard_coverage.py` |
| Pre-receive rules name every bad path | `backend/tests/unit/test_git_validation.py::test_unsafe_names_are_refused_per_path`, `::test_names_that_differ_only_in_case_clash`, `::test_a_symlink_is_refused` |

## Settings

Defined in `backend/src/inkstave/core/config/groups.py` (`GitSettingsMixin`); listed in `.env.example` and
[the admin guide](../admin-guide.md#git-access-spec-121).

| Variable | Default | Effect |
|---|---|---|
| `GIT_ENABLED` | `false` | Serve the Git routes and show the UI |
| `GIT_REPOS_ROOT` | `/data/git` | Bare repositories; a persistent volume shared by every replica |
| `GIT_MAX_PUSH_BYTES` | `52428800` | Largest pack accepted; also the body cap of `git-receive-pack` |
| `GIT_OPERATION_TIMEOUT_S` | `60` | Deadline per operation and the lock's expiry and wait |
| `RATE_LIMIT_GIT_AUTH` | `20/300` | Failed token attempts per IP |

The upload limit for `git-upload-pack` bodies is `MAX_UPLOAD_BYTES`. The `/api/` location of nginx needs
`client_max_body_size` of at least `GIT_MAX_PUSH_BYTES` (`infra/nginx/default.conf`).

## Points of attention

- **The database commit and the live edits are two steps.** The CRDT rows reference the document rows, so the
  tree commits first. If the process dies between the two, the project holds the pushed tree and the live text lags;
  the next flush reconciles it. `main` moves after the live edits, so no client sees a commit the project lacks.
- **Pushes run their own sessions.** `receive_pack` and `snapshot_locked` open sessions from the session factory and
  commit them. The request session is not used for them, because it commits only when the route returns.
- **History records the origin.** `history_updates.origin` is set per captured version. The push flushes history
  before and after its own capture, so one version never mixes origins.
- **Upload-pack is not streamed from the source.** dulwich builds the pack in memory, so the bound is the project's
  size. Receive-pack bodies are read in full up to the cap.
- **A lost repository loses Git history, not the project.** Snapshots restore the current tree as one commit. That is
  also why `GIT_REPOS_ROOT` is safe to lose in a backup plan.
- **Restores are edits.** A history restore is a new edit in the project, so it appears in the next fetch, not as a
  Git commit of its own.
- **One replica is still the rule for collaboration.** The Git lock is in Redis, so Git itself is safe across
  replicas that share the volume, but live text updates reach only rooms on the same instance (see
  [collab.md](collab.md)).
- **Divergence from the spec.** Spec 121 named the snapshot `snapshot_project`; the code uses `snapshot_locked`
  (under the lock) and `repository.snapshot_commit` (the commit itself). The glossary follows the code.
