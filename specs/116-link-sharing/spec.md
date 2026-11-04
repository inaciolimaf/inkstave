# Spec 116 — Share by link (requirements)

## 1. Summary
E-mail invites need the owner to know every address. Competitors also offer a link: whoever has it, and an
account, joins. This spec adds a view link and an edit link per project, owned by the owner, with rotation and
revocation, built on the existing membership and capability model.

## 2. Context & dependencies
- **Depends on:** 33 (invites, memberships), 34 (capabilities), 109 (shared projects appear in the list).
- **Affected areas:** backend `projects/sharing`, `projects/models`; frontend `sharing`, routes; docs.

## 3. Goals
- Per project, at most one active link per role, `viewer` and `editor`.
- Owner: create (turn on), copy, rotate (new token, old one stops), turn off.
- Opening `/join/{token}` while signed in: a preview (project name, owner, role) and a Join button. Signed out:
  sign in or register, then back to the same preview.
- Joining creates an `active` membership with the link's role and remembers the link it came from.
- Turning a link off (or rotating it) takes back exactly what that link granted. A member the link created leaves
  the project. A member the link upgraded returns to their previous role. Members whose role the owner set by hand,
  or who accepted an e-mail invite, are not touched.
- A member never loses role by joining: a viewer who opens the edit link becomes editor; an editor opening the view
  link stays editor.

## 4. Non-goals
- Anonymous access without an account (needs a whole guest model: later, if ever).
- Link expiry dates and passwords on links.
- Links that grant `owner`.

## 5. Detailed requirements

### 5.1 Data model (one migration)
`project_share_links`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `project_id` | FK projects, cascade | |
| `role` | text, check `viewer`/`editor` | |
| `token_hash` | text, unique | SHA-256 of the token, like invites (`hash_token`) |
| `created_by` | FK users, `SET NULL` | |
| `created_at`, `revoked_at` | timestamptz | |

Partial unique index `(project_id, role) WHERE revoked_at IS NULL`.

`project_memberships` gains:
- `via_link_id` UUID nullable, FK `project_share_links` `SET NULL`: set when a membership is created or upgraded by
  a link;
- `role_before_link` text nullable, check `viewer`/`editor`: the role held before a link upgraded it, null when the
  link created the membership.

Both are cleared when the owner changes the role by hand or the member accepts an e-mail invite: from then on the
access no longer depends on the link.

### 5.2 Backend / API
All under `/api/v1`, errors in the standard envelope.

| Method and path | Who | Does | Errors |
|---|---|---|---|
| `GET /projects/{id}/share-links` | owner | Active links, without tokens (the token is shown only once, at creation) | 403 `not_project_owner`, 404 |
| `POST /projects/{id}/share-links` `{role}` | owner | Create, or rotate if one is active: revokes the old row, creates a new one, 201 with the raw `token` and `url` | 403, 404, 422 |
| `DELETE /projects/{id}/share-links/{link_id}` | owner | Turn off; 204 | 403, 404 `share_link_not_found` |
| `GET /share-links/{token}` | signed in | Preview: project name, owner display name, role, and `already_member_role` | 404 `share_link_not_found` (revoked, unknown or project deleted: same answer) |
| `POST /share-links/{token}/join` | signed in | Join or upgrade; returns the membership | 404 |

- Revoking runs in one transaction: set `revoked_at`; then, for memberships with `via_link_id = link.id` and role
  other than `owner`, restore `role_before_link` when it is set, or else set `status = 'left'`; then clear both
  columns on those rows.
- Because open WebSockets are not re-authorized (known gap), document it in `docs/system/sharing.md`: a removed
  link member keeps a socket until it closes. Do not fix it here.
- Rate limits: `POST /share-links/{token}/join` and `GET /share-links/{token}` use a named policy
  `RATE_LIMIT_SHARE_LINK` (default `30/60` per user), added to settings, `.env.example` and
  `docs/admin-guide.md`.
- Raw tokens never appear in logs; the access log redaction must cover `/share-links/` paths like `?token=`.
- Add the new routes to the guard audit list (`_HANDLER_GUARDED`) where they authorize in the handler.

### 5.3 Frontend
- Share dialog (`frontend/src/modules/sharing`): a section "Share with a link" (PT "Compartilhar por link") with two
  rows, "Anyone with the link can view" / "… can edit", each with a switch, Copy, and Rotate (with a confirmation that
  people who joined through the old link lose access).
- The token is only known at creation. After a reload the row shows "Link on" with Rotate to get a new copyable
  link. Show this plainly: "For safety the link is shown only once. Rotate to get a new one."
- Route `/join/:token` (`frontend/src/routes/join.tsx`) behind `RequireAuth` (which keeps the return path):
  preview card and Join; after joining, navigate to the project. Already a member at an equal or higher role:
  "You already have access" and Open.
- Members list in the share dialog marks link members ("via link").
- All strings in `en` and `pt` (`sharing` namespace). Fits 390 px.

## 6. Overleaf reference (study only — never copy)
- `services/web/app/src/Features/TokenAccess/` — read-only and read-write tokens, and how token members differ from
  invited members.
- `services/web/frontend/js/features/share-project-modal/` — the link-sharing section.

## 7. Acceptance criteria
1. Owner turns on the edit link; B opens it, joins, sees the project in "Shared with me", and can type.
2. Owner rotates the edit link: B loses access; the old URL answers "This link is no longer valid".
3. C was invited by e-mail as viewer, then opened the edit link and became editor. Turning the edit link off
   returns C to viewer; C is not removed.
4. An editor opening the view link stays editor.
5. A non-owner gets 403 on the link routes; a stranger gets 404.
6. The raw token is never stored and never logged.

## 8. Test plan
- **Integration:** every route and error; join idempotence; upgrade and restore on revoke; rotate revokes the old
  members; deleted project → 404 on preview and join; rate limit; guard audit passes.
- **Vitest:** share dialog section (switch, copy, rotate confirmation), join page states.
- **Budget:** no slow test.

## 9. Rules and guarantees
| Rule | Guarantee |
|---|---|
| Only a token hash is stored | `test_share_link_stores_hash_only` |
| Revoking a link removes only what the link granted | `test_revoke_restores_previous_role`, `test_revoke_removes_link_only_members` |
| A link never lowers a role | `test_view_link_does_not_downgrade_editor` |
| A revoked or unknown token looks the same | `test_revoked_and_unknown_token_both_404` |

## 10. Definition of Done
- [ ] §5 implemented, §7 passes, §8 green.
- [ ] `docs/system/sharing.md` updated (table, routes, revoke rule, socket caveat); settings documented.
- [ ] Glossary: "Share link" → `ProjectShareLink` → "Link de compartilhamento".
