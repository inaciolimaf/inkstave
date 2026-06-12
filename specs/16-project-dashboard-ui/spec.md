# Spec 16 — Project Dashboard UI (requirements)

## 1. Summary

This spec delivers the authenticated **project dashboard**: the first screen a
logged-in user sees. It lists the user's projects (as a table on desktop, cards
on narrow viewports), and lets them **create**, **rename**, **delete** and
**open** a project. It is a frontend-only spec that consumes the project CRUD
API from spec 11. All async mutations use optimistic updates with toast
feedback, and every list state (loading, empty, error) is handled explicitly.

## 2. Context & dependencies

- **Depends on:**
  - **09** — frontend foundation: the Vite/React/TS app, Tailwind + shadcn/ui,
    the router, the typed API client (with JWT access/refresh handling), the
    auth pages and the "protected route" wrapper, and toast infrastructure.
  - **11** — project model & CRUD API: the REST endpoints this UI calls.
- **Unlocks:**
  - **17** (file tree UI) and **18** (editor) — both are reached via the
    "open project" navigation introduced here (the `/projects/:projectId`
    editor route shell).
- **Affected areas:** frontend only. No backend, collab, infra changes.

> **API contract note.** The exact request/response shapes below mirror what
> spec 11 (`11-project-model-crud`) defines. If spec 11's implemented shapes
> differ, treat **spec 11 as authoritative** and adapt the client/types here.
> This spec assumes the spec-11 endpoints in §5.4.

## 3. Goals

- Render a list of the current user's projects fetched from the spec 11 API.
- Create a new project via a modal form (name input, validation).
- Rename a project inline-or-via-modal (consistent, accessible).
- Delete a project behind a confirmation dialog.
- Open a project by navigating to its editor route (`/projects/:projectId`).
- Handle loading / empty / error states for the list explicitly.
- Apply optimistic updates for create/rename/delete and roll back on failure.
- Show toast notifications on success and failure of every mutation.
- Be keyboard-accessible and screen-reader-friendly.

## 4. Non-goals (explicitly out of scope)

- The file tree, editor, autosave, compile, preview (specs 17–24).
- Sharing/collaborators, roles, invites (Phase 4).
- Tags, folders-of-projects, archive, trash, "leave project", clone/copy.
- Pagination/infinite scroll *if* spec 11 returns the full list; only add
  client-side search/sort if §5.3 lists it (it does — search + sort are in
  scope, server pagination is not).
- Server-side rendering. Inkstave's frontend is a Vite SPA.

## 5. Detailed requirements

### 5.1 Data model (if any)

None (frontend-only). TypeScript types only, colocated with the API client.

```ts
// frontend/src/features/projects/types.ts
export interface Project {
  id: string;            // uuid
  name: string;
  ownerId: string;
  createdAt: string;     // ISO 8601
  updatedAt: string;     // ISO 8601
}

export interface ProjectListResponse {
  projects: Project[];
}

export interface CreateProjectRequest { name: string }
```

> Naming: follow spec 11's actual field names. If spec 11 returns `created_at`
> (snake_case) on the wire, the API client converts to camelCase at the boundary
> so React components only ever see camelCase. Do not leak snake_case into
> components.

### 5.2 Backend / API (if any)

None. This spec adds no endpoints. It only *calls* the spec 11 API (see §5.4).

### 5.3 Frontend / UI

#### 5.3.1 Routes (React Router, established in spec 09)

| Route | Component | Guard | Purpose |
| --- | --- | --- | --- |
| `/` | redirect → `/projects` | authed | home |
| `/projects` | `ProjectsPage` | **protected** (redirect to `/login` if no session) | the dashboard |
| `/projects/:projectId` | `EditorPage` (shell only) | **protected** | editor route target; full content arrives in specs 17–19 |

- The protected-route wrapper from spec 09 is reused; this spec does not
  reinvent auth gating.
- `EditorPage` in this spec is a **placeholder shell** that reads `:projectId`,
  shows the project name (fetched via `GET /projects/{id}`) and a "loading
  editor…" placeholder. Its full 3-pane content is built in spec 18. The only
  requirement here is that "Open" navigates to it and it renders without error.

#### 5.3.2 Component tree

```
ProjectsPage
├── ProjectsHeader
│   ├── <h1> "Your projects"
│   ├── ProjectSearchInput          (shadcn Input, client-side filter)
│   ├── ProjectSortSelect           (shadcn Select: "Last modified" | "Name A–Z" | "Created")
│   └── NewProjectButton            (shadcn Button → opens CreateProjectDialog)
├── ProjectListView                 (switches on query state)
│   ├── ProjectListSkeleton         (loading)
│   ├── ProjectListEmpty            (empty: no projects at all)
│   ├── ProjectListNoResults        (empty: filter matched nothing)
│   ├── ProjectListError            (error + Retry button)
│   ├── ProjectTable                (md+ viewport, shadcn Table)
│   │   └── ProjectRow* (name link, updatedAt, RowActionsMenu)
│   └── ProjectCardGrid             (< md viewport, shadcn Card)
│       └── ProjectCard* (name link, updatedAt, RowActionsMenu)
├── CreateProjectDialog             (shadcn Dialog + Form)
├── RenameProjectDialog             (shadcn Dialog + Form, controlled by selected project)
└── DeleteProjectDialog             (shadcn AlertDialog, destructive confirm)
```

- `RowActionsMenu` is a shadcn **DropdownMenu** with items: **Open**, **Rename**,
  **Delete** (Delete styled destructive). It is the same component in table and
  card layouts.
- Prefer shadcn/ui primitives (`Dialog`, `AlertDialog`, `DropdownMenu`, `Table`,
  `Card`, `Input`, `Select`, `Button`, `Skeleton`, `Form`, `Sonner`/`Toaster`).
  Do not hand-write modal/menu/table CSS.

#### 5.3.3 State management

- **Server state:** use the data-fetching layer established by spec 09. If spec
  09 adopted **TanStack Query**, use it (`useQuery(['projects'], …)`,
  `useMutation`). If spec 09 used a plain client + local state, follow that
  pattern instead. The spec **assumes TanStack Query** for caching, optimistic
  updates and invalidation; if absent, the implementer adds it as a frontend dep
  (it is within the React data-layer remit, not a stack substitution) and notes
  it in `docs/`.
- **Local UI state (per page):**
  - `searchTerm: string`
  - `sortKey: 'updatedAt' | 'name' | 'createdAt'`
  - `dialog: { type: 'create' | 'rename' | 'delete' | null; project?: Project }`
- Derived `visibleProjects` = filter(by name, case-insensitive) → sort(by key).

#### 5.3.4 Props (key components)

```ts
ProjectTable({ projects, onOpen, onRename, onDelete }:
  { projects: Project[];
    onOpen: (p: Project) => void;
    onRename: (p: Project) => void;
    onDelete: (p: Project) => void; })

CreateProjectDialog({ open, onOpenChange, onCreated }:
  { open: boolean;
    onOpenChange: (v: boolean) => void;
    onCreated?: (p: Project) => void; })

RenameProjectDialog({ open, onOpenChange, project }:
  { open: boolean; onOpenChange: (v: boolean) => void; project: Project | null; })

DeleteProjectDialog({ open, onOpenChange, project }:
  { open: boolean; onOpenChange: (v: boolean) => void; project: Project | null; })
```

#### 5.3.5 User interactions

1. **Create.** Click **New project** → `CreateProjectDialog` opens with a single
   "Project name" text input focused. Submit (Enter or "Create") →
   `POST /projects`. On success: dialog closes, toast "Project created",
   list updates (optimistic insert at top, reconciled on response). The new
   project may optionally be opened immediately only if §7 doesn't require
   staying; default: stay on dashboard.
2. **Rename.** Row menu → **Rename** → `RenameProjectDialog` opens pre-filled
   with the current name, text selected. Submit → `PATCH /projects/{id}`.
   Optimistic name change in the list; toast "Project renamed".
3. **Delete.** Row menu → **Delete** → `DeleteProjectDialog` (AlertDialog)
   asks "Delete '<name>'? This cannot be undone." with **Cancel** /
   **Delete** (destructive). Confirm → `DELETE /projects/{id}`. Optimistic
   removal; toast "Project deleted".
4. **Open.** Click the project name link, or row menu → **Open**, navigates to
   `/projects/:projectId`.
5. **Search.** Typing in the search input filters the visible list live
   (debounced ~150 ms, client-side). Clearing restores the full list.
6. **Sort.** Selecting a sort option reorders the visible list.

#### 5.3.6 Validation

- Project name: required; trimmed; length **1–255** chars; reject all-whitespace.
- Use a schema validator (**Zod** via shadcn `Form` + `react-hook-form`, the
  pattern spec 09 establishes). Inline error message under the input; submit
  button disabled while invalid or while the mutation is pending.
- Surface server-side validation/uniqueness errors (e.g. 409/422 from spec 11)
  as a field-level or toast error; do not silently swallow them.

#### 5.3.7 Loading / empty / error states

- **Loading (initial):** `ProjectListSkeleton` — shadcn `Skeleton` rows (≈6),
  no layout shift.
- **Empty (no projects):** `ProjectListEmpty` — friendly illustration/text
  "No projects yet" + primary **Create your first project** button (opens the
  create dialog).
- **Empty (search no match):** `ProjectListNoResults` — "No projects match
  '<term>'" + **Clear search**.
- **Error (list fetch failed):** `ProjectListError` — message + **Retry**
  (refetch). 401 is handled by the API client's refresh/redirect from spec 09,
  not shown as a list error.
- **Mutation pending:** affected row shows a subtle pending style; dialog submit
  button shows a spinner and is disabled. On failure: optimistic change rolls
  back and an error toast appears.

#### 5.3.8 Accessibility

- One `<h1>` per page ("Your projects").
- The project table uses semantic `<table>` markup (shadcn Table) with a
  `<caption>` (visually hidden) "Your projects".
- All dialogs use shadcn `Dialog`/`AlertDialog` (focus trap, `Esc` to close,
  focus returns to the trigger, `aria-labelledby`/`aria-describedby` wired by
  the primitive).
- `DropdownMenu` is keyboard-operable (arrow keys, Enter, Esc) via the shadcn
  primitive; the trigger has an accessible name (`aria-label="Project actions"`).
- Destructive **Delete** is reachable by keyboard and clearly labelled; the
  AlertDialog default focus is on **Cancel**, not **Delete**.
- Toasts are announced via an `aria-live` region (Sonner provides this).
- Color is never the only signal (destructive items also carry an icon/label).
- All interactive elements have visible focus rings (Tailwind `focus-visible`).

### 5.4 Real-time / jobs / external integrations

None. The dashboard calls these **spec 11** REST endpoints through the spec 09
API client (JWT in `Authorization` header, refresh handled by the client):

| Action | Method & path | Request body | Success | Notable errors |
| --- | --- | --- | --- | --- |
| List projects | `GET /projects` | – | `200` `{ projects: Project[] }` | `401` (→ client refresh/redirect) |
| Get one | `GET /projects/{id}` | – | `200` `Project` | `404`, `403` |
| Create | `POST /projects` | `{ name: string }` | `201` `Project` | `422` (validation), `409` (dup, if spec 11 enforces) |
| Rename | `PATCH /projects/{id}` | `{ name: string }` | `200` `Project` | `404`, `422`, `409` |
| Delete | `DELETE /projects/{id}` | – | `204` | `404`, `403` |

> If spec 11 used `PUT` instead of `PATCH`, or a different list envelope, follow
> spec 11. Keep all HTTP details inside `frontend/src/features/projects/api.ts`
> so components never touch fetch/axios directly.

### 5.5 Configuration

- No new env vars. The API base URL/client come from spec 09's config.
- If TanStack Query is newly added, register its `QueryClientProvider` at the
  app root (spec 09's provider tree) and note it in `docs/`.

## 6. Overleaf reference (study only — never copy)

> Read these in `../overleaf/` to understand the **UI/UX approach only**.
> Inkstave's components are written independently. Paths verified to exist.

- `services/web/frontend/js/features/project-list/` — overall dashboard
  structure: how the project list, toolbar and actions are organised.
- `services/web/frontend/js/features/project-list/components/table/project-list-table.tsx`
  and `.../table/project-list-table-row.tsx` — table/row layout and per-row
  action affordances (study layout, not code).
- `services/web/frontend/js/features/project-list/components/modals/rename-project-modal.tsx`
  and `.../modals/delete-project-modal.tsx` — rename/delete modal UX (titles,
  confirm wording, button placement).
- `services/web/frontend/js/features/project-list/components/new-project-button.tsx`
  — the create-project entry point UX.
- `services/web/frontend/js/features/project-list/context/project-list-context.tsx`
  — how list state, filtering and sorting are organised (concept only; Inkstave
  uses TanStack Query + local state instead).

Inkstave differences: we use shadcn/ui primitives + Tailwind (not Bootstrap/
React-Bootstrap), TanStack Query for server state, and we cover only owner CRUD
(no tags/archive/trash).

## 7. Acceptance criteria

1. **Given** a logged-in user with ≥1 project, **when** they visit `/projects`,
   **then** their projects render in a table (md+ viewport) showing name and
   last-modified, fetched from `GET /projects`.
2. **Given** the list is still loading, **then** a skeleton placeholder is shown
   (no spinner-less blank screen, no layout shift when data arrives).
3. **Given** the user has zero projects, **then** the empty state with a
   "Create your first project" call-to-action is shown.
4. **Given** the list fetch fails, **then** an error state with a working
   **Retry** button is shown; clicking Retry refetches.
5. **Given** the create dialog is open, **when** the user submits a valid name,
   **then** `POST /projects` is called, the dialog closes, a success toast
   appears, and the new project appears in the list.
6. **Given** an empty or whitespace-only name, **then** the create/rename submit
   button is disabled and an inline validation message is shown; no request is
   sent.
7. **Given** a rename is submitted, **then** the list shows the new name
   optimistically before the response, `PATCH /projects/{id}` is called, and a
   success toast appears; **if** the request fails the name reverts and an error
   toast appears.
8. **Given** the delete dialog is confirmed, **then** the project is removed from
   the list optimistically, `DELETE /projects/{id}` is called, and a success
   toast appears; **if** it fails the project reappears and an error toast shows.
9. **Given** the delete dialog, **then** default keyboard focus is on **Cancel**,
   and `Esc` closes the dialog without deleting.
10. **Given** the user clicks a project name (or "Open"), **then** the app
    navigates to `/projects/:projectId` and the editor shell renders that
    project's name without error.
11. **Given** text in the search box, **then** the list filters live by name
    (case-insensitive); a non-matching term shows the "no results" state with a
    **Clear search** action.
12. **Given** the sort select is changed, **then** the visible list reorders
    accordingly.
13. **Accessibility:** the page has exactly one `<h1>`; all dialogs trap focus
    and restore it on close; the row actions menu is fully keyboard-operable;
    automated `axe` checks report no serious/critical violations on the
    dashboard.

## 8. Test plan

> All tests combined across the project must keep the suite under 2 minutes.
> Backend is not exercised here; the spec-11 API is mocked (MSW or the spec 09
> test API-client mock).

- **Unit (Vitest + React Testing Library):**
  - `ProjectTable`/`ProjectCard`: render rows from a fixture; name link points
    to `/projects/:id`; actions menu exposes Open/Rename/Delete.
  - `ProjectListView` state machine: loading→skeleton, empty→empty state,
    error→error+Retry, success→table; "no results" when filter excludes all.
  - `CreateProjectDialog`: validation (empty/whitespace/255+ chars disables
    submit, shows message); valid submit calls the create mutation with trimmed
    name; pending disables submit.
  - `RenameProjectDialog` / `DeleteProjectDialog`: pre-fill, confirm wording,
    Esc-to-cancel, destructive focus default.
  - Optimistic update + rollback: mock mutation rejection and assert the list
    reverts and an error toast is requested.
  - Search filter + sort: pure derivation of `visibleProjects`.
- **Integration (Vitest + RTL + MSW):**
  - Full dashboard with MSW serving `GET /projects`; create → list shows new
    item; rename → name updates; delete → item removed. Assert the correct
    HTTP method/path/body via MSW handlers.
- **E2E (Playwright):** one flow — log in (seeded user) → land on `/projects`
  → create a project (mocked or against the real spec 11 API per the e2e
  harness from spec 04) → see it in the list → rename it → open it (URL becomes
  `/projects/:id`) → go back → delete it → confirm it's gone. Keep this to a
  single spec file to stay within budget.
- **Performance/budget note:** all unit/integration tests use mocked HTTP (no
  network, no real backend), so they run in milliseconds. The single Playwright
  flow is the only browser-driven test and is kept short.

## 9. Definition of Done

- [ ] All requirements in §5 implemented.
- [ ] All acceptance criteria in §7 pass.
- [ ] All tests in §8 written and green.
- [ ] Full suite runs in < 2 minutes.
- [ ] Lint/format/type-check clean (ESLint + Prettier, TS strict).
- [ ] No new env vars required; if TanStack Query was added, it is documented in
      `docs/` and wired at the app root.
- [ ] shadcn/ui primitives used for dialogs/table/menu/toasts (no hand-rolled
      modal/menu CSS).
- [ ] No Overleaf code copied.
