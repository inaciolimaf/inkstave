# Refactor 20 — Editor & File-Tree UI (specs 16–19)

An inward quality pass over the Phase-2 frontend: project dashboard (16), file
tree (17), CodeMirror editor (18) and REST autosave (19). **No features, no
behaviour change** — the only production edit is dead-code removal; everything
else is added a11y/regression test coverage and an audit.

## Baseline (before)

- **Vitest:** 122 tests green (~4.6 s). **Playwright:** 5 flows green.
- `tsc --noEmit`, ESLint, Prettier: clean, no warnings.

## Method

`pnpm test` for the green baseline; `pnpm build` for tree-shaking; extended
ESLint (`no-unused-vars`) + grep for unused exports; added **`jest-axe`**
(dev-only) to run `axe` on the dashboard, file-tree and editor in jsdom; manual
read of the autosave/DnD/CodeMirror-lifecycle/optimistic-rollback paths.

The surface was already in good shape (the specs were built test-first), so most
findings are **verified-clean** plus **coverage gaps**; no behaviour-changing
bug was found.

## Findings

| id | area | category | decision | rationale / change |
| --- | --- | --- | --- | --- |
| F-001 | `file-tree/tree-utils.ts` | dead code | **fixed** | Removed unused `listFolders` (+ its test) — left over from a "Move to…" picker that shipped as the "Move to root" action instead. |
| F-002 | dashboard / tree / editor | accessibility | **fixed (test)** | Added `jest-axe` assertions: `ProjectsPage`, `FileTreePanel` (+ ARIA-tree check), and `EditorPane` (with a doc open, LaTeX-editor region) report **no serious/critical violations** (AC4). |
| F-003 | dashboard rename, tree delete | missing tests | **fixed (test)** | Closed a missing-tests gap with optimistic-**rollback** regression tests: a failed rename reverts the name + error toast; a failed delete restores the node + error toast. (Surfaced the jsdom nuance that an open Radix dialog `aria-hidden`s the background — assert after closing it.) |
| F-004 | autosave, DnD | missing tests | **fixed (test)** | Closed a missing-tests gap: autosave flushes on `visibilitychange → hidden`; a folder dropped **onto itself** issues no move. |
| F-005 | `FileTreeNode` re-renders | performance | **skipped** | Nodes consume context, so a context change re-renders all of them; `React.memo` wouldn't help and the cost is negligible for realistic project trees. Over-memoizing rejected per the spec. |
| F-006 | `sortNodes` per render | performance | **skipped** | Re-sorting a folder's children each render is cheap; memoizing adds complexity for little value. |
| F-007 | `autosave.lastSavedAt` | dead-ish | **skipped** | Returned but not yet shown (no "Saved 2m ago" UI). Kept: it's part of spec-19's documented `DocAutosaveState` and is harmless; a future indicator can use it. |
| F-008 | CodeMirror lifecycle | correctness | **verified, no change** | The `EditorView` is created once and reconfigured via compartments (theme/font/wrap/keymap/editable); switching docs dispatches a `changes` transaction, not a recreate — already test-guarded (specs 18/19). |
| F-009 | autosave conflict / offline | correctness | **verified, no change** | 409 never blind-overwrites (conflict dialog); single-flight + coalesce; capped backoff with manual retry — all test-guarded (spec 19). |
| F-010 | data flow / cache keys | consistency | **verified, no change** | HTTP is confined to each feature's `api.ts`; snake_case is mapped at the boundary; query keys include `projectId` (no cross-project cache leakage). |

## Applied edits

- **Production:** removed `listFolders` from `tree-utils.ts` (dead code) — no
  behaviour change.
- **Tests (+6, all green):** 3 `jest-axe` a11y specs; dashboard rename-rollback;
  file-tree delete-rollback + drop-onto-self; autosave visibility-flush.
- **Dev dependency:** `jest-axe` (MIT) — runs only in the fast Vitest tier; no
  measurable budget impact.
- **Dropped dev dependency:** `@axe-core/playwright` was listed in
  `devDependencies` but never imported or used (no `AxeBuilder`/`@axe-core/playwright`
  references in `e2e/` or `src/`). Accessibility checks run via `jest-axe` in the
  Vitest tier (F-002), so the unused Playwright axe binding was removed.

## After

- **Vitest:** 128 tests green (~8 s with the axe specs). **Playwright:** 5 flows
  green (unchanged).
- `tsc`, ESLint, Prettier: clean, no new warnings.
- No feature/scope added; no spec 11–14 API contract changed; no Overleaf code
  introduced.
