# Spec 109 — Shared projects on the dashboard (requirements)

## 1. Summary
`list_projects` in `backend/src/inkstave/modules/projects/catalog/service.py` filters on `Project.owner_id`, so a
collaborator reaches a shared project only by its URL, and a former owner loses the project from the list after
a transfer. This spec lists projects by active membership and gives the dashboard a filter and an owner column,
as competing editors do. It is a bug fix first, so it comes before the feature specs.

## 2. Context & dependencies
- **Depends on:** 11 (catalog), 16 (dashboard UI), 33 (memberships).
- **Unlocks:** 116 (link sharing), whose joiners must find the project in their list.
- **Affected areas:** backend `projects`, frontend `projects`, docs.

## 3. Goals
- `GET /api/v1/projects` returns every live project where the caller has an `active` membership.
- Each item says the caller's role and who the owner is.
- The dashboard filters All / Owned by me / Shared with me, and shows only the actions the role allows.
- A non-owner can leave a shared project from the list.

## 4. Non-goals
- Folders, tags, archive or trash for projects.
- Search on the server (the existing client-side filter, if any, stays).
- Changing who may rename or delete (still owner only).

## 5. Detailed requirements

### 5.1 Data model
- No new table. Add an index on `project_memberships (user_id, project_id) WHERE status = 'active'` in a new
  Alembic migration, so the membership join does not scan.

### 5.2 Backend / API
`GET /api/v1/projects`

| Parameter | Values | Default |
|---|---|---|
| `scope` | `all`, `owned`, `shared` | `all` |
| `limit` | 1–100 | 50 |
| `offset` | ≥ 0 | 0 |

- `owned`: membership role `owner`. `shared`: role `editor` or `viewer`. `all`: both.
- Soft-deleted projects and memberships with status `left` or `pending` never appear.
- Order stays `updated_at DESC`, then `id` for a stable page.
- Each item of `ProjectRead` gains `role` (`owner` | `editor` | `viewer`) and
  `owner: {id, display_name}`. `owner_id` stays for compatibility.
- One query: join `project_memberships` and `users` (for the owner's display name). No N+1; assert the
  statement count in the test.
- An unknown `scope` answers 422 `validation_error`.
- Regenerate `docs/api/openapi.json` and `frontend/src/api/types.ts` (`make web-types`).

### 5.3 Frontend / UI
- `frontend/src/modules/projects/`: a segmented control above the list, "All" / "Owned by me" / "Shared with me"
  (PT: "Todos" / "Meus" / "Compartilhados comigo"). The choice is kept in the URL (`?scope=`) so a reload keeps it.
- A column (a line under the name on a phone) with the owner: "You" for the caller's own, otherwise the owner's
  display name. A small role mark for `editor` and `viewer` ("Can edit" / "Can view").
- Action menu by role: owner keeps rename, download, delete; editor and viewer get download and **Leave project**,
  which calls `DELETE /projects/{id}/members/{own id}` after a confirmation and removes the row.
- Empty state for "Shared with me": "Nothing shared with you yet. Projects others invite you to appear here."
- Every string in `en` and `pt` locale files of the `projects` namespace. Must fit 390 px.

### 5.4 Configuration
None.

## 6. Overleaf reference (study only — never copy)
- `services/web/app/src/Features/Project/ProjectListController.mjs` — how owned, shared and token-access projects
  are merged into one list with filters.
- `services/web/frontend/js/features/project-list/` — the filter sidebar and owner column.

## 7. Acceptance criteria
1. Given A invites B as editor and B accepts, when B lists projects, then the project appears with `role: editor`
   and `owner.display_name` of A.
2. Given B left the project, it no longer appears for B.
3. Given A transfers ownership to B, A still sees the project, now as `editor`.
4. `scope=owned` and `scope=shared` partition `scope=all`.
5. A soft-deleted project appears for nobody.
6. On the dashboard, B sees no rename or delete, sees Leave, and leaving removes the row.
7. The filter survives a reload.

## 8. Test plan
- **Integration:** `backend/tests/integration/test_projects_api.py`: shared listing, scopes, left membership,
  transfer, deleted project, owner field, one query for a page (count statements with an SQLAlchemy event).
- **Vitest:** filter control and URL state; action menu per role; leave flow with a mocked API; empty state.
- **E2E:** extend the collab or sharing flow in `frontend/e2e/flows/` only if it already logs in two users;
  otherwise Vitest is enough. Do not run e2e without asking the user (see memory of spec 107).
- **Budget:** no new slow test.

## 9. Rules and guarantees
| Rule | Guarantee |
|---|---|
| A user's list is every live project they actively belong to | `test_list_includes_shared_projects` |
| Scopes partition the list | `test_scopes_partition_all` |
| A left membership hides the project | `test_left_member_does_not_see_project` |
| One page is one query | `test_list_projects_single_query` |
| Non-owners see no owner-only action | `project-actions.test.tsx` |

## 10. Definition of Done
- [ ] §5 implemented, §7 passes, §8 tests green, suite within budget.
- [ ] `docs/system/projects.md` and `docs/system/sharing.md` updated; the "Shared projects are not listed" point of
      attention and the `list_projects` entry in `docs/known-gaps.md` removed.
- [ ] Glossary: "Shared with me" → `scope=shared` → "Compartilhados comigo"; "Leave project" → "Sair do projeto".
- [ ] `make lint types docs`, `make web-test` clean.
