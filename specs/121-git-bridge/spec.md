# Spec 121 — Git access to projects (requirements)

## 1. Summary
Writers who use Git want to clone a project, work locally, and push back, as Overleaf's Git integration allows. This
spec serves one bare repository per project over Git's Smart HTTP protocol, inside the backend, using the pure-Python
library **dulwich**, so the images need no `git` binary. The web project stays the source of truth. A fetch commits the
current state first. A push must be a fast-forward of that state, and its changes become ordinary edits: tree
operations for files, minimal CRDT edits for text.

## 2. Context & dependencies
- **Depends on:** 12–14 (tree, documents, files), 28–31 (CRDT, history), 101 (name and path validation), 109.
- **Affected areas:** backend new module `git` (above `projects` in the module order), `core/http` (body limit),
  `auth` (tokens); frontend `settings`, `editor`; config; deployment docs. New dependency: `dulwich` (Apache-2.0 or
  GPL-2.0+ dual licence; use it under Apache-2.0, record that in the ADR).

## 3. Goals
- `git clone https://<host>/api/v1/git/projects/<project_id>.git` works with a token as the password.
- One branch, `main`. Pushing any other ref is refused with a clear message.
- Fetch: the server flushes open documents, and if the project differs from `main`'s tree, commits it as
  "Inkstave <noreply@inkstave>" with the message "Update from Inkstave".
- Push: accepted only as a fast-forward of the current `main`. Otherwise Git shows the server's message: "Pull first:
  the project changed in Inkstave."
- An accepted push is applied: added, changed, deleted and renamed files. Text documents change through the CRDT
  as minimal edits, so collaborators' concurrent edits elsewhere survive and the change shows up live. The history
  records each changed document with the origin `git-push` and the pusher's name.
- Personal access tokens: create (shown once), list (name, prefix, created, last used), revoke, optional expiry.

## 4. Non-goals
- Syncing with GitHub or GitLab (a later spec could add a remote mirror).
- Branches, tags, merge on the server, LFS, submodules.
- SSH access.
- Keeping Git history across a history restore in the web app: a restore is a new edit, and appears in the next fetch.

## 5. Detailed requirements

### 5.1 Data model (one migration)
`git_access_tokens`: `id` UUID PK, `user_id` FK cascade, `name` text 1–100, `token_hash` text unique (SHA-256),
`prefix` text (first 12 characters, for display), `created_at`, `last_used_at`, `expires_at` nullable, `revoked_at`
nullable. At most 20 active tokens per user (409 `token_limit`).

`git_repo_state`: `project_id` PK FK cascade, `head` text (commit sha), `updated_at`. This is the server's record of
what `main` was after its last snapshot or push. It is used to detect drift and to rebuild a lost repository.

### 5.2 Repository storage
- Bare repos at `{GIT_REPOS_ROOT}/{project_id}.git`, created on first use. If the directory is lost, it is recreated
  from the project as a single new commit (history in Git is lost, the project is not). State that in the admin guide.
- All repo work for a project runs under a Redis lock `git:lock:{project_id}` (timeout `GIT_OPERATION_TIMEOUT_S`), so
  two replicas sharing the volume never interleave.
- dulwich is synchronous: run every repo operation in `asyncio.to_thread`, wrapped in `asyncio.timeout`.

### 5.3 HTTP endpoints (Smart HTTP)
| Method and path | Needs |
|---|---|
| `GET /api/v1/git/projects/{id}.git/info/refs?service=git-upload-pack` | token, `DOC_READ` |
| `POST /api/v1/git/projects/{id}.git/git-upload-pack` | token, `DOC_READ` |
| `GET /api/v1/git/projects/{id}.git/info/refs?service=git-receive-pack` | token, `DOC_WRITE` and `FILE_WRITE` |
| `POST /api/v1/git/projects/{id}.git/git-receive-pack` | same |

- Auth: HTTP Basic. The username is ignored and the password is the token. A missing or bad token gets 401 with
  `WWW-Authenticate: Basic realm="Inkstave"`. A non-member gets 404, a member without write access gets 403 on
  receive-pack. Failed attempts count against `RATE_LIMIT_GIT_AUTH` per IP (default `20/300`).
- Session-JWT auth is **not** accepted on these routes, and tokens are not accepted anywhere else.
- The dumb HTTP protocol is not served.
- `info/refs` for either service runs the snapshot of §3 first.
- Upload-pack responses stream; receive-pack bodies are read up to `GIT_MAX_PUSH_BYTES`. The request body limit
  middleware gets an exemption for `git-receive-pack` paths with that cap. nginx's `client_max_body_size` on `/api/`
  must be at least the cap: document it in `docs/admin-guide.md` and the nginx config comment.
- Add these routes to the guard audit's handler-guarded list with a test.

### 5.4 Applying a push
1. Pre-receive: the only ref is `refs/heads/main`, the new commit descends from `git_repo_state.head`, and the
   diff old → new tree is validated: every path passes `validate_name_segment` and the zip-import path rules, files
   respect the upload size and type rules (`UPLOAD_ALLOWED_EXTENSIONS`, sniffing), text files are valid UTF-8 and under
   `MAX_DOCUMENT_BYTES`, the tree stays under `TREE_MAX_NODES`. Any failure refuses the whole push with a message per
   path, and nothing changes.
2. Apply in one database transaction: create folders, create or update `file` entities and blobs, create `doc` entities,
   delete removed entities, and detect renames (dulwich's rename detection, similarity ≥ 90 %) as moves so documents
   keep their identity and history.
3. After the commit, for each changed text document, compute a line diff old blob → new blob and apply it to the live
   document through the collab `DocumentManager` as minimal edits (the same path as a history restore, origin
   `git-push`). The edits are applied to the current live text, located by context like `rebaseHunks`. A hunk that no
   longer matches (a collaborator changed those lines since the fetch) is applied anyway by replacing the region,
   and the response reports the file in a warning line ("main.tex: lines 40–52 were also edited in Inkstave; the pushed
   version was kept").
4. Update `git_repo_state.head`, set `last_used_at` on the token, write an audit log line.
5. Blob writes that fail after step 2 leave the project consistent with the old content: write blobs before the
   transaction commits, and delete new blobs on rollback.

### 5.5 Frontend
- Settings → "Git access tokens" (PT "Tokens de acesso Git"): create with name and optional expiry, the token shown once
  with Copy, list, revoke with confirmation.
- Editor bar menu → "Git" (PT "Git"): the clone URL with Copy, the command `git clone <url>`, and a note that the
  password is a token, with a link to the settings section. Hidden when `GIT_ENABLED=false` (exposed through the
  existing public config endpoint).
- Strings in `en` and `pt`.

### 5.6 Configuration
| Variable | Default | Effect |
|---|---|---|
| `GIT_ENABLED` | `false` | Serve the Git routes and show the UI |
| `GIT_REPOS_ROOT` | `/data/git` | Where bare repos live; must be a persistent volume shared by all backend replicas |
| `GIT_MAX_PUSH_BYTES` | `52428800` | Largest accepted pack |
| `GIT_OPERATION_TIMEOUT_S` | `60` | Deadline per Git operation and the lock timeout |
| `RATE_LIMIT_GIT_AUTH` | `20/300` | Failed token attempts per IP |

All in settings, `.env.example` and `docs/admin-guide.md`. `GIT_ENABLED` defaults to off, so existing servers are not
affected. The admin guide lists the volume to add before turning it on. Docker files are not changed in this spec
(user decision): the operator adds the volume.

## 6. Overleaf reference (study only — never copy)
- Overleaf's Git bridge is a separate Java service (`services/git-bridge/` in some versions, not in Community Edition).
  If present in `../overleaf/`, read it for the snapshot-then-push model only.
- `services/web/app/src/Features/` … token handling for Git (`PersonalAccessToken`) where present.

## 7. Acceptance criteria
1. With `GIT_ENABLED=true`, `git clone` with a valid token gets the project's current files, including an edit made a
   second earlier in the browser.
2. Editing `main.tex` locally, committing and pushing makes the change appear live in an open browser, and in History as
   a Git push by that user.
3. A push after a web edit that was not pulled is refused with "Pull first…". After `git pull` and push, it is accepted.
4. Renaming a file locally and pushing moves the entity: its history is kept.
5. Pushing `../evil.tex`, a 60 MB file, or a disallowed binary refuses the whole push, and the project is unchanged.
6. A viewer's token can clone and cannot push (403). A stranger's token gets 404. A revoked token gets 401.
7. With `GIT_ENABLED=false`, the routes answer 404 and the UI hides Git.

## 8. Test plan
- **Unit:** token hashing and parsing; pre-receive validation table; rename detection mapping; the minimal-edit diff
  applied to a `pycrdt` text.
- **Integration:** drive the Smart HTTP endpoints with dulwich's own client against the ASGI app (no network, no `git`
  binary): clone, push, non-fast-forward refusal, invalid push, roles, revoked token, snapshot idempotence (two fetches
  with no change make one commit), lock held across replicas (two concurrent pushes, one waits).
- **Smoke (optional, `@slow`):** real `git` CLI clone and push, out of the default run.
- **Budget:** repos in a tmp dir per test; tiny projects.

## 9. Rules and guarantees
| Rule | Guarantee |
|---|---|
| A push is all or nothing | `test_invalid_push_changes_nothing` |
| A push never silently overwrites unpulled web edits | `test_non_fast_forward_refused` |
| Pushed text arrives as minimal live edits | `test_push_applies_through_crdt` |
| Tokens are stored as hashes and work only on Git routes | `test_git_token_hash_only`, `test_git_token_rejected_on_api` |
| Git is off unless enabled | `test_git_disabled_404` |

## 10. Definition of Done
- [ ] ADR (dulwich, sync model, conflict policy) written first; §5 implemented, §7 passes, §8 green, within budget.
- [ ] New `docs/system/git.md` and its index line; `security.md` (tokens, auth), `projects.md`, `history.md` (origin
      `git-push`) updated; settings documented; `docs/user-guide.md` has a Git section.
- [ ] Glossary: "Git access token" → `GitAccessToken` → "Token de acesso Git"; "Snapshot commit" → `snapshot_project` →
      "—".
