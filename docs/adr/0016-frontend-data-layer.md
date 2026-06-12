# ADR 0016 — Frontend server-state with TanStack Query

- **Status:** Accepted
- **Date:** 2026-06-09
- **Context spec:** 16 — Project Dashboard UI

## Context

The project dashboard (spec 16) is the first screen that reads and mutates
server data (list / create / rename / delete projects). It needs caching across
components, optimistic updates with rollback, and explicit loading / empty /
error states. Spec 09 established a typed `apiClient` (fetch + JWT refresh) plus
local React state, but no server-state cache.

## Decision

Adopt **TanStack Query v5** (`@tanstack/react-query`) as the frontend
server-state layer, wired at the app root via `QueryClientProvider` in
`main.tsx`. This is within the React data-layer remit (not a stack substitution):
the existing `apiClient` remains the transport; TanStack Query only manages
caching, request state, and mutation lifecycles on top of it.

- All project HTTP lives in `features/projects/api.ts` (snake_case ↔ camelCase
  mapping at the boundary); components never call `fetch`.
- `useProjects()` reads `["projects"]`; mutations (`useCreateProject`,
  `useRenameProject`, `useDeleteProject`) apply **optimistic** cache updates with
  snapshot rollback on error and `invalidateQueries` on settle.
- The `QueryClient` defaults to `retry: false` so failures surface promptly (the
  list error state with Retry, and error toasts) rather than retrying silently.
- Toaster: **sonner** (`@/components/ui/sonner`) mounted once at the root for the
  `aria-live` toast region.

## Consequences

- New deps: `@tanstack/react-query`, `sonner`, and the shadcn/Radix primitives
  used by the dashboard (`dialog`, `alert-dialog`, `dropdown-menu`, `select`,
  `table`, `skeleton`). Dev: `@axe-core/playwright` for the a11y e2e gate.
- Later data-driven screens (file tree 17, editor 18) reuse this layer and
  pattern instead of bespoke fetching.
- Tests mock `fetch` with a small stateful fake (no MSW dependency); the single
  Playwright flow runs against the Vite app with the API mocked via `page.route`
  and asserts no serious/critical `axe` violations on the dashboard.

## Alternatives considered

- **Plain `apiClient` + `useState`/`useEffect`** — would re-implement caching,
  dedup, optimistic rollback and invalidation by hand across screens; rejected.
- **Redux Toolkit Query / SWR** — viable, but TanStack Query is the most common
  fit for this shadcn/React stack and has first-class optimistic-update ergonomics.
- **MSW for tests** — cleaner HTTP assertions, but adds a dependency and worker
  setup; a stateful `fetch` fake keeps the unit suite dependency-light and fast.
