# Spec 122 — Project search and replace (requirements)

## 1. Summary
A thesis is split over many files. Renaming a term, a `\label` and its `\ref`s, or a macro today means opening each
file, and the editor has no search at all (no `@codemirror/search`). This spec adds a **Search** tab to the file
drawer that searches every document of the project and replaces one match or all of them. Came from the
competitor comparison of 2026-11-04 (Overleaf Server Pro 6.1 shipped project-wide search).

## 2. Context & dependencies
- **Depends on:** 31 (Yjs binding), 47 (the diff-review bridge that writes through a short-lived provider), 111 (the
  project index, which already fetches every document's text and keeps the open one live).
- **Affected areas:** frontend only, docs. No backend route: the texts are the index's, the writes are CRDT updates.

## 3. Goals
- One query box with three toggles: match case, whole word (letters and digits of any script, and `_`), regular
  expression (JavaScript syntax; `^`/`$` per line; `$1`, `$&`, `$<name>`, `$$` in the replacement).
- Results grouped by file in path order, each row the line number and the line with the match marked; a total
  "N results in M files". At most 1000 rows listed; past it the panel says so.
- Click a row → the drawer closes, the file opens, and the matched text is selected and scrolled into view.
- Replace one (a button per row) and Replace all (asks first, counting every match of the project, past the cap
  too). A viewer searches but sees no replace.
- Ctrl+Shift+F (Cmd+Shift+F) opens the drawer on Search with the query selected.

## 4. Non-goals
- Searching binary files, or the PDF.
- A server-side search route (the agent keeps `search_project`).
- In-file Ctrl+F (a later change may add `@codemirror/search`).
- Undoing a replace with Ctrl+Z: the editor's undo manager tracks local typing only. History restores it.

## 5. Detailed requirements

### 5.1 The module — `frontend/src/modules/project-search/`
- Pure: `matcher.ts` (`buildMatcher`: query + options → `RegExp` with `g`, or an error message, or `null` when
  empty; tries the `u` flag first, then without), `find.ts` (`findMatches` with line, column, groups and the line's
  text; empty matches skipped; `previewOf`), `replace.ts` (`expandReplacement`, `replacementEdits`, `applyEdits`,
  `relocate`), `search-project.ts` (`searchSources`, `MAX_RESULTS = 1000`).
- `replace-actions.ts`: `replaceMatch` and `replaceInFiles` over a `TextWriter` whose `transformContent(path, edit)`
  reads the live text, computes the edits on it and writes them in one step. A single replace relocates its match
  on the live text (same text, same column, a line that reads the same; among identical lines the same rank) and
  writes nothing when it cannot (`StaleMatchError`, a toast says the results are fresh now).
- `use-project-search.ts` holds the state; the query settles for 200 ms before searching.
- The module imports no other module.

### 5.2 Wiring
- `project-index` exposes `texts` (every indexed document, the open one live) and `setDocText` (writes a new text
  into its query cache, so the results follow a replace without a refetch). Past the index caps only the open file
  is searched, and the panel says so.
- `diff-review` gains `applySplicesToYText` (origin `search-replace`, last splice first, one transaction) and
  `transformContent` on the editor bridge, which waits at most 10 s for the document's first sync.
  Each splice touches only its range, so a collaborator's edit between two matches survives.
- `FileDrawer` gets a third tab, Search (PT "Buscar"), and can be told its tab by the host; the drawer is 20rem wide
  on that tab. The tab is remembered as before.
- `revealLine` takes an optional `{column, length}` and selects it; `jumpToSource` passes it through a file switch.
- All strings in `en` and `pt` (`search` namespace, plus `drawer.search`). Fits 390 px (drawer at most 80% wide).

## 6. Overleaf reference (study only — never copy)
- None read. The behaviour is described from Overleaf's 6.1.0 release note.

## 7. Acceptance criteria
1. "rede neural" in two files lists 3 results in 2 files, grouped by file.
2. Clicking a result opens its file with the match selected.
3. Replace all asks "Replace 3 matches in 2 files?" and, on confirm, changes both files.
4. A regex `\\(label|ref)\{fig:x\}` → `\\$1{fig:result}` renames a label and its references, not `fig:xy`.
5. A collaborator typing between two matches keeps the typing after a replace all.
6. A replace whose line changed since the search writes nothing.
7. A viewer has no replace controls.
8. An invalid regular expression shows its error, not an exception.

## 8. Test plan
- **Vitest:** `matcher.test.ts`, `find.test.ts`, `replace.test.ts`, `search-project.test.ts`,
  `replace-actions.test.ts`, `search-panel.test.tsx`; `crdt-apply.test.ts` (splices and a concurrent edit);
  `file-drawer.test.tsx` (third tab); `sync-decoration.test.ts` (span selection).
- **Budget:** pure functions and component tests, no slow test.

## 9. Rules and guarantees
| Rule | Guarantee |
|---|---|
| A replace never lands on a line the writer did not see | `replace-actions.test.ts`, "writes nothing when the match's line changed" |
| Replace all keeps a concurrent edit elsewhere | `crdt-apply.test.ts`, "keeps a collaborator's edit between two replaced matches" |
| Replace all asks first and counts every match | `search-panel.test.tsx`, "replaces all only after a confirmation that counts every match" |
| A viewer cannot replace | `search-panel.test.tsx`, "offers no replace to a viewer" |

## 10. Definition of Done
- [ ] §5 implemented, §7 passes, §8 green, `make web-test` and `make web-budget` pass.
- [ ] `docs/system/frontend.md` describes the module and the wiring.
- [ ] Glossary: "Project search" → `project-search`, `SearchPanel` → "Buscar".
