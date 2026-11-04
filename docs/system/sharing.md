# Sharing and authorization

Who can open a project and what they can do in it. An owner shares a project by e-mail invite; the
invitee accepts and becomes a member with the role `editor` or `viewer`. Every project route then checks
the caller's role against one capability matrix. Specs 33 (collaborators), 34 (access control) and 35
(the guard audit).

## Where it is

| File | Role |
|---|---|
| `backend/src/inkstave/modules/projects/access` | Package: the matrix, `role_for`, the FastAPI gate |
| `backend/src/inkstave/modules/projects/access/capabilities.py` | `Capability`, `capabilities_for`: the single matrix |
| `backend/src/inkstave/modules/projects/access/deps.py` | `require_capability`, the dependency on project routes |
| `backend/src/inkstave/modules/projects/access/service.py` | `role_for`, `InsufficientRoleError`, the `AuthorizationService` facade |
| `backend/src/inkstave/modules/projects/sharing` | Package: the sharing service, public surface in `__init__.py` |
| `backend/src/inkstave/modules/projects/sharing/members.py` | List, change role, remove, leave, transfer ownership |
| `backend/src/inkstave/modules/projects/sharing/invites.py` | Create, list, revoke, preview, accept, decline |
| `backend/src/inkstave/modules/projects/sharing/common.py` | `require_member`, `require_owner`, `membership_of`, `MemberInfo` |
| `backend/src/inkstave/modules/projects/sharing/errors.py` | Typed domain errors |
| `backend/src/inkstave/modules/projects/routes/sharing.py` | Member and invite routes |
| `backend/src/inkstave/modules/projects/schemas/sharing.py` | Request and response models |
| `backend/src/inkstave/modules/projects/models/membership.py` | `ProjectMembership`, `MembershipRole`, `MembershipStatus` |
| `backend/src/inkstave/modules/projects/models/invite.py` | `ProjectInvite`, `InviteRole`, `InviteStatus` |
| `frontend/src/modules/sharing` | Share dialog, accept page, `usePermissions`, `isReadOnly` |
| `frontend/src/routes/invite.tsx` | Route `/invite/:token`, behind `RequireAuth` |
| `backend/tests/unit/test_authz_matrix.py` | Exhaustive matrix test |
| `backend/tests/integration/test_authz_guard_coverage.py` | Guard audit over every `{project_id}` route |
| `backend/tests/integration/test_access_control_api.py` | Role behaviour over HTTP |
| `backend/tests/integration/test_sharing_api.py` | Invite flows over HTTP |
| `backend/tests/integration/test_sharing_api_members.py` | Member flows over HTTP |
| `backend/tests/integration/test_sharing_api_authz.py` | 403 and 404 on sharing routes |
| `backend/tests/integration/test_sharing_service.py` | Service-level rules |

## Data

Both tables are created by `backend/migrations/versions/20260610_0010_a1c2e3f40915_create_sharing_tables.py`,
which also backfills an active `owner` membership for every live project.

`project_memberships`

| Column | Notes |
|---|---|
| `id`, `created_at`, `updated_at` | Standard mixins |
| `project_id`, `user_id` | FKs with `ON DELETE CASCADE`; unique together (`uq_membership_project_user`) |
| `role` | `owner`, `editor`, `viewer` (check constraint) |
| `status` | `active`, `pending`, `left` (check constraint). The code writes only `active` and `left` |

`uq_membership_one_owner` is a partial unique index on `project_id` where `role = 'owner'`: at most one
owner per project at the database level. `ix_project_memberships_user_active` is a partial index on
`(user_id, project_id)` where `status = 'active'`, which the dashboard listing joins on (spec 109; migration
`backend/migrations/versions/20261104_1200_f6a2b8c4d1e9_spec109_membership_active_index.py`). `create_project` in
`backend/src/inkstave/modules/projects/catalog/service.py` adds the creator's owner membership.
`projects.owner_id` is kept in step with it by `transfer_ownership`.

`project_invites`

| Column | Notes |
|---|---|
| `id`, `created_at`, `updated_at` | Standard mixins |
| `project_id`, `invited_by` | FKs with `ON DELETE CASCADE` |
| `email` | `CITEXT`, normalized to lower case on creation |
| `role` | `editor` or `viewer` (check constraint): an invite never grants `owner` |
| `token_hash` | SHA-256 hex of the opaque token (`hash_token`), unique |
| `status` | `pending`, `accepted`, `declined`, `revoked`, `expired` |
| `expires_at`, `responded_at` | `responded_at` is set on accept, decline and revoke |

`uq_invite_one_pending` is a partial unique index on `(project_id, email)` where `status = 'pending'`.

## Routes

All routes require a bearer token. Errors use the standard envelope `{"error": {"type", "message",
"details", "request_id"}}` as plain JSON (see Points of attention). The table lists `error.type`.

| Method and path | What it does | Errors |
|---|---|---|
| `GET /api/v1/projects/{project_id}/members` | Active members, oldest first. Any member | 404 `project_not_found` |
| `PATCH /api/v1/projects/{project_id}/members/{user_id}` | Set `editor` or `viewer`. Owner only | 403 `not_project_owner`; 400 `invalid_role`, `cannot_change_owner_role`; 404 `project_not_found`, `member_not_found` |
| `DELETE /api/v1/projects/{project_id}/members/{user_id}` | Remove a member (owner) or leave (own id) | 403 `not_project_owner`; 400 `owner_cannot_leave`; 404 `project_not_found`, `member_not_found` |
| `POST /api/v1/projects/{project_id}/members/transfer` | Make `to_user_id` the owner. Owner only | 403 `not_project_owner`; 400 `not_a_member`; 404 `project_not_found` |
| `GET /api/v1/projects/{project_id}/invites` | Pending invites, newest first. Owner only | 403 `not_project_owner`; 404 `project_not_found` |
| `POST /api/v1/projects/{project_id}/invites` | Create or refresh an invite, 201 with the raw `token`. Owner only | 403 `not_project_owner`; 409 `already_member`; 404 `project_not_found`; 422 `validation_error` |
| `DELETE /api/v1/projects/{project_id}/invites/{invite_id}` | Revoke. Owner only | 403 `not_project_owner`; 404 `project_not_found`, `invite_not_found` |
| `GET /api/v1/invites/{token}` | Preview for the accept screen | 404 `invite_not_found`; 410 `invite_gone` |
| `POST /api/v1/invites/{token}/accept` | Join the project | 403 `invite_email_mismatch`; 404 `invite_not_found`; 410 `invite_gone` |
| `POST /api/v1/invites/{token}/decline` | Decline | 404 `invite_not_found`; 410 `invite_gone` |
| `GET /api/v1/projects/{project_id}/permissions` | Caller's `role` and sorted `capabilities`. Lives in `backend/src/inkstave/modules/projects/routes/projects.py` | 404 `project_not_found` |

## How it works

### Roles and capabilities

`capabilities_for(role, compile_for_viewers=True)` is the single matrix. Non-member is `None` and has
an empty set.

| Capability | owner | editor | viewer |
|---|---|---|---|
| `project_read` | yes | yes | yes |
| `project_write` (rename, settings) | yes | no | no |
| `project_delete` | yes | no | no |
| `project_share` | yes | no | no |
| `doc_read` | yes | yes | yes |
| `doc_write` | yes | yes | no |
| `file_read` | yes | yes | yes |
| `file_write` | yes | yes | no |
| `collab_read` | yes | yes | yes |
| `collab_write` | yes | yes | no |
| `compile` | yes | yes | yes, unless `COMPILE_ALLOWED_FOR_VIEWERS=false` |
| `project_download` | yes | yes | yes |

`project_share` is defined but no route checks it. Sharing routes use `require_member` and
`require_owner` from the service, which compare the role directly.

### The dependency model

`require_capability(cap)` builds one FastAPI dependency. It binds `project_id` from the path, gets the
user from `get_current_user`, calls `_resolve`, and returns the loaded `Project` to the handler.

`_resolve` loads the live project and the caller's active role in one outer-join query. The result is
cached per project in `request.state.authz_cache`, so several guards on one request share a query. The
gate then decides:

1. Project missing, soft-deleted, or caller has no active membership: `ProjectNotFoundError` (404).
2. Role lacks `cap`, with the setting applied: `InsufficientRoleError` (403 `insufficient_role`).
3. Otherwise the project goes to the handler.

Each dependency carries a `__authz_capability__` marker. The guard audit walks the dependency tree of
every route with `{project_id}` in its path and fails unless it finds the marker or the path is on the
audited `_HANDLER_GUARDED` list. The listed routes authorize in the handler: sharing, `/permissions`,
the compile and import SSE routes, and the agent routes.

`AuthorizationService` is a facade over `role_for` and `capabilities_for`. No production code
instantiates it.

### How other modules check access

| Module | Where | Check | Denial |
|---|---|---|---|
| Documents, files, tree | `backend/src/inkstave/modules/projects/routes/documents.py`, `backend/src/inkstave/modules/projects/routes/files.py`, `backend/src/inkstave/modules/projects/routes/tree.py` | `require_capability` with `DOC_READ`, `DOC_WRITE`, `FILE_READ`, `FILE_WRITE` | 404, 403 |
| Project CRUD | `backend/src/inkstave/modules/projects/routes/projects.py` | `PROJECT_READ`, `PROJECT_WRITE`, `PROJECT_DELETE`, `PROJECT_DOWNLOAD` | 404, 403 |
| Compile REST | `backend/src/inkstave/modules/compile/routes/compile.py` | `COMPILE` on trigger, latest, status, cancel, outputs, PDF and log | 404, 403 |
| Compile SSE | `compile_events` in the same file | `role_for` is not `None`: any member. Token in the query string | 404 |
| Compile job | `_settle_if_unauthorized` in `backend/src/inkstave/modules/compile/queue/jobs.py` | Re-checks `COMPILE` for `requested_by` at pickup | Compile fails with a stored reason |
| SyncTeX, problems | `backend/src/inkstave/modules/compile/routes/synctex.py`, `backend/src/inkstave/modules/compile/routes/logparse.py` | `PROJECT_READ` | 404 |
| History | `backend/src/inkstave/modules/history/routes.py` | `PROJECT_READ` to read, `DOC_WRITE` to restore or change labels | 404, 403 |
| Collab WebSocket | `_authorize` in `backend/src/inkstave/modules/collab/ws/connection.py` | `role_for` at join; `COLLAB_WRITE` sets `can_write` | Close 4404 missing project or document, 4403 non-member |
| Agent REST | `_require_member` in `backend/src/inkstave/modules/agent/routes.py` | Live project, then `role_for` is not `None` | 404, then 403 `not_project_member` |
| Agent tools | `authorize` in `backend/src/inkstave/modules/agent/tools/base.py` | `PROJECT_READ` per tool call, plus `DOC_WRITE` when `require_write` is set | `ToolError` code `forbidden` |
| Import SSE | `backend/src/inkstave/modules/projects/routes/project_import.py` | `role_for` is not `None` | 404 |

### The 403 and 404 policy

- A non-member of a project sees the same 404 as for a missing project, so existence is not leaked.
- A member whose role is too low gets 403.
- Soft-deleted projects count as missing. `role_for` returns `None` for them.
- Sharing follows the same split through `require_member` (404) and `require_owner` (404, then 403).

Two surfaces differ on purpose and do tell an authenticated user that the project exists: the agent
REST routes (403 for a non-member) and the collab WebSocket (4403 for a non-member).

### Viewer rules

A viewer reads everything in the project, joins the collab room, downloads the zip, and compiles by
default. The server enforces read-only: `doc_write` and `file_write` routes answer 403, and
`_handle_update` drops the viewer's Yjs updates before they are applied, stored or relayed. The viewer
still receives other people's edits and awareness. The UI reads `/permissions` through `usePermissions`
and goes read-only with `isReadOnly`, which is only a convenience. Viewers can use the agent's read
tools; `propose_edit` is refused because it requires `DOC_WRITE`.

### `COMPILE_ALLOWED_FOR_VIEWERS`

Default `true`. When `false`, `require_capability` and `/permissions` drop `compile` from the viewer's
set. All `COMPILE`-gated routes then answer 403 for a viewer, including the read routes for status, PDF
and log. The flag changes nothing else in the matrix.

### Invites

`create_invite` requires the owner, lower-cases the address, and raises `already_member` if that
address belongs to an active member. It generates a token, stores only the hash, and reuses the pending
row for the same address if there is one: the role, token, expiry and inviter are replaced, so the
earlier link stops working. The route then calls `notify_invite`, described in the notifications doc,
and returns the raw token to the owner.

`accept_invite` looks the invite up by token hash, then:

1. If already `accepted`: returns the current membership if the caller is an active member, else 410.
2. If not pending or past expiry: 410.
3. If the caller's e-mail differs, ignoring case: 403 `invite_email_mismatch`.
4. `_grant_membership` creates the membership or re-activates a `left` one with the invite's role. An
   existing owner keeps `owner`.
5. Marks the invite `accepted`.

`decline_invite` needs a pending, unexpired invite and sets `declined`. `revoke_invite` sets `revoked`
on a pending invite and does nothing on any other status. `get_invite_preview` answers 410 for a
non-pending invite, an expired one, or one whose project is soft-deleted.

### Members and ownership transfer

`remove_member` with the caller's own id is a leave: the owner gets 400, anyone else moves to `left`. The
dashboard's "Leave project" action (spec 109) calls this route with the caller's own id after a confirmation,
and the project leaves the caller's `GET /api/v1/projects` list at once.
With another id it requires the owner and moves the target to `left`. The row stays, so a later invite
re-activates it.

`transfer_ownership` requires the owner and an active target that is not the caller. It demotes the old
owner to `editor`, flushes, promotes the target, flushes, then sets `projects.owner_id`. The two flushes
keep `uq_membership_one_owner` satisfied at each step. The old owner stays as an editor, and there is no
undo route.

## Rules and guarantees

| Invariant | Test |
|---|---|
| Every role and capability pair matches the matrix | `backend/tests/unit/test_authz_matrix.py::test_every_role_capability_pair` |
| A non-member has no capabilities | `backend/tests/unit/test_authz_matrix.py::test_non_member_has_no_capabilities` |
| The viewer compile flag removes `compile` | `backend/tests/unit/test_authz_matrix.py::test_viewer_compile_flag_toggles_compile` |
| Every `{project_id}` route is guarded or on the audited list | `backend/tests/integration/test_authz_guard_coverage.py::test_every_project_scoped_route_is_guarded` |
| The audited list has no dead entries | `backend/tests/integration/test_authz_guard_coverage.py::test_handler_guarded_allowlist_routes_exist` |
| Owner-only project writes: 403 for members, 404 for outsiders | `backend/tests/integration/test_access_control_api.py::test_project_write_is_owner_only` |
| Members compile by default; outsiders get 404 | `backend/tests/integration/test_access_control_api.py::test_compile_allows_members` |
| `/permissions` reflects the role; outsiders get 404 | `backend/tests/integration/test_access_control_api.py::test_permissions_per_role` |
| Agent routes answer 403 to a non-member | `backend/tests/integration/test_agent_api.py::test_session_create_authz` |
| Owner-only sharing routes answer 403 to a member | `backend/tests/integration/test_sharing_api_authz.py::test_non_owner_owner_only_endpoints_403` |
| Sharing routes answer 404 to a stranger | `backend/tests/integration/test_sharing_api_authz.py::test_cross_project_isolation_404` |
| Inviting an active member is 409 | `backend/tests/integration/test_sharing_api_authz.py::test_invite_already_member_409` |
| An invite cannot grant `owner` | `backend/tests/integration/test_sharing_service.py::test_invite_schema_rejects_owner_role` |
| Re-inviting refreshes the row and rotates the token | `backend/tests/integration/test_sharing_service.py::test_create_invite_refreshes_existing_pending` |
| Accept needs the invited address, ignoring case | `backend/tests/integration/test_sharing_service.py::test_accept_requires_matching_email`, `backend/tests/integration/test_sharing_service.py::test_accept_is_case_insensitive_on_email` |
| Accept is idempotent and creates one membership | `backend/tests/integration/test_sharing_api.py::test_accept_creates_membership_and_is_idempotent` |
| Decline creates no membership | `backend/tests/integration/test_sharing_api.py::test_decline_creates_no_membership` |
| An expired invite answers 410 on accept and decline | `backend/tests/integration/test_sharing_api.py::test_expired_invite_returns_410`, `backend/tests/integration/test_sharing_api.py::test_expired_invite_decline_returns_410` |
| The owner cannot leave | `backend/tests/integration/test_sharing_api_members.py::test_owner_cannot_leave` |
| A user's dashboard lists every live project they actively belong to, with their role and the owner | `backend/tests/integration/test_projects_api.py::test_list_includes_shared_projects` |
| A left membership hides the project from the list | `backend/tests/integration/test_projects_api.py::test_left_member_does_not_see_project` |
| A former owner still sees a transferred project, as editor | `backend/tests/integration/test_projects_api.py::test_transfer_keeps_project_for_former_owner` |
| A soft-deleted project appears for nobody | `backend/tests/integration/test_projects_api.py::test_soft_deleted_project_appears_for_nobody` |
| The `owned` and `shared` scopes partition `all` | `backend/tests/integration/test_projects_api.py::test_scopes_partition_all` |
| The listing of a page is one query over memberships | `backend/tests/integration/test_projects_api.py::test_list_projects_single_query` |
| `owner` is reachable only through transfer | `backend/tests/integration/test_sharing_service.py::test_change_role_transitions_and_rejects_owner` |
| Transfer leaves one owner, demotes the old one, updates the project row | `backend/tests/integration/test_sharing_api_members.py::test_transfer_ownership_single_owner` |
| Transfer needs an active member | `backend/tests/integration/test_sharing_service.py::test_transfer_to_non_member_rejected` |
| The migration backfills owner memberships | `backend/tests/integration/test_migrations.py::test_sharing_migration_backfills_owner_membership` |
| A viewer's Yjs update is dropped and not relayed | `backend/tests/integration/test_collab_ws_access.py::test_viewer_update_is_dropped` |
| A non-member cannot join a room | `backend/tests/integration/test_collab_ws_access.py::test_non_member_join_rejected_4403` |
| A viewer cannot propose an edit but can use read tools | `backend/tests/integration/test_agent_tools_authz.py::test_viewer_cannot_propose_but_can_read` |
| The compile job re-checks access at pickup | no dedicated test |
| `COMPILE_ALLOWED_FOR_VIEWERS=false` at route level | no dedicated test; only the matrix function is tested |
| The request-scoped role cache does one lookup | no dedicated test |

## Settings

Defined in `backend/src/inkstave/core/config/groups.py`.

| Variable | Default | Effect |
|---|---|---|
| `COMPILE_ALLOWED_FOR_VIEWERS` | `true` | Viewers hold `compile` |
| `INVITE_TTL_DAYS` | `14` | Pending invite lifetime, reset on refresh |
| `FRONTEND_URL` | `http://localhost:5173` | Base of the accept link |

## Points of attention

- **Error format.** The API does not emit `application/problem+json`. The handlers in
  `backend/src/inkstave/core/exception_handlers.py` return a JSON `ErrorEnvelope`. The text field is
  `error.message`; there is no `detail` field. `error.details` holds structured validation data.
- **Message language.** All `message` strings in `backend/src/inkstave/modules/projects/access` and
  `backend/src/inkstave/modules/projects/sharing` are English. `frontend/src/modules/sharing/useSharing.ts`
  and `frontend/src/modules/sharing/AcceptInvitePage.tsx` show the server message when present, so a
  Portuguese UI shows these English strings instead of its translated fallback.
- **The `expired` status is not persisted by the routes.** `_require_pending` and `decline_invite` set
  `expired`, flush, then raise `InviteGoneError`. The unit of work rolls back on any exception, so the row
  stays `pending`. Nothing sweeps invites either. Pending invites past their expiry stay in `list_invites`
  because it does not filter on `expires_at`. The 410 is still correct.
- **`COMPILE_ALLOWED_FOR_VIEWERS` is not applied everywhere.** The compile job calls `capabilities_for`
  without the flag, so a job queued by a viewer before the flag changed still runs. `compile_events` accepts
  any member, so a viewer can still follow the SSE stream.
- **Open WebSockets are not re-authorized.** `role_for` runs at join and `can_write` is fixed for the
  connection. A removed member keeps receiving updates, and a demoted editor can keep writing, until the
  socket closes. The sharing service has no link to the collab module.
- **Accept skips the live-project check.** `accept_invite` does not test `deleted_at`. On a soft-deleted
  project it returns 200 and the next request gets 404.
- **Decline has no e-mail check.** Any authenticated holder of the token can decline. The owner receives
  the raw token in the create response.
- **Check order on accept.** An expired invite answers 410 even to the wrong user. The already-accepted
  branch skips the e-mail check, but it only reports the caller's own membership.
- **No rate limit.** The invite routes carry no `rate_limit_named` dependency, so an owner can trigger
  invite e-mail without a cap.
- **Two 404 types.** `ProjectAccessNotFoundError` in the facade uses `not_found`, while the production gate
  raises `project_not_found`. The facade has no production caller, so clients see only the second.
- **Stale references.** Docstrings in `backend/src/inkstave/modules/projects/access/capabilities.py` and
  `backend/src/inkstave/modules/projects/access/service.py` cite `authorization/dependencies.py`, and
  `backend/src/inkstave/modules/projects/sharing/__init__.py` cites `sharing_errors` and siblings. Those
  names no longer exist.
