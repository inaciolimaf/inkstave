# Spec 111 — Document outline (requirements)

## 1. Summary
A long paper is navigated by its structure. This spec adds an outline panel listing `\part` … `\subparagraph` of
the whole project, following `\input` and `\include` from the main document, and highlighting the section that
holds the cursor. The parsing lives in a small pure TypeScript module, the **project index**, which spec 112 will
extend with labels and bibliography keys.

## 2. Context & dependencies
- **Depends on:** 18 (CodeMirror), 28–29 (live `Y.Text`), 107 (layout: one bar, file drawer).
- **Unlocks:** 112 (autocomplete reads labels and file list from the index).
- **Affected areas:** frontend only, docs.

## 3. Goals
- Parse sectioning commands, starred forms and the optional short title (`\section[Short]{Long}`) → the long title
  is shown, the short one ignored.
- Follow `\input{x}`, `\include{x}`, `\subfile{x}` and `\import{dir}{x}` from the main document, with or without
  the `.tex` extension, relative to the project root (and to `dir` for `\import`). Cycles are cut.
- Show one tree for the project in document order, with the file name as a faint hint per entry.
- Click → open that file and put the cursor on the line, scrolled into view.
- The entry containing the cursor is highlighted and kept visible; it follows typing and clicks.
- Live: the open file's entries update as you type (debounced 300 ms); other files update when they are saved or
  opened, and when the tree changes.

## 4. Non-goals
- Drag to reorder sections.
- Figures and tables in the outline.
- Server-side parsing. (The agent's section locator stays as it is; the two parsers may differ.)

## 5. Detailed requirements

### 5.1 The project index — `frontend/src/modules/project-index/`
- `parse-structure.ts`: `parseStructure(text: string): StructureItem[]` where
  `StructureItem = {kind: "section"|"label"|"include", level?: number, title?: string, target?: string, line: number}`.
  Pure, no DOM. It skips comments (`%` not preceded by `\`), `verbatim`, `lstlisting`, `minted` and
  `comment` environments, and does not split titles on nested braces (`\section{A {B} C}` → `A {B} C`).
  Levels: part 0, chapter 1, section 2, subsection 3, subsubsection 4, paragraph 5, subparagraph 6.
- `labels` are collected now (kind `label`) even though the outline does not show them; 112 uses them.
- `use-project-index.ts`: a hook that holds `Map<docId, StructureItem[]>`. The open document is parsed from the live
  `Y.Text`; the others are fetched once through the documents API and re-fetched when a doc is saved by someone
  else (a collab update arrives for a doc the hook knows) or the tree changes. A cap of 200 documents and 2 MB of
  text; above it, the outline shows only the open file with a notice.
- `resolve-includes.ts`: builds the ordered tree from the main document. The main document is the one compile uses
  (`main_file`, otherwise `pickStartDocument`'s rule).
- The module has a public `index.ts`. `make boundaries`-style checks on the frontend (`frontend/tests/`
  boundaries suite) must pass: `editor` imports it, it imports nothing from `editor`.

### 5.2 Frontend / UI
- `FileDrawer` gets two tabs: **Files** and **Outline** (PT: "Arquivos" / "Estrutura"). The last chosen tab is
  remembered in `localStorage` (wrapped in try/catch).
- On desktop wide screens (≥ 1280 px) the outline can also be pinned as a narrow column left of the text; pinning
  is a toggle in the outline header, remembered like the tab. Below 1280 px only the drawer exists.
- Outline rows: indentation by level, the title in the UI font, the file name of entries from other files in a
  smaller muted style. Long titles truncate with the full text in `title`.
- The current section row has the "selected" token background and `aria-current="location"`.
- Empty state: "No sections yet. Add \section{…} to see the structure." with the code in monospace.
- The tree is a `role="tree"` with arrow-key navigation; Enter opens.
- All strings in `en` and `pt` (`editor` namespace). Fits 390 px (drawer only on phone).

### 5.3 Configuration
None.

## 6. Overleaf reference (study only — never copy)
- `services/web/frontend/js/features/outline/` — outline pane, current-section highlight, and how it scrolls.
- `services/web/frontend/js/features/source-editor/utils/tree-operations/outline.ts` — the idea of walking sections
  (Overleaf uses its own Lezer grammar, which Inkstave does not have: see ADR 0018).

## 7. Acceptance criteria
1. `main.tex` with `\input{chapters/intro}` shows the sections of `chapters/intro.tex` in place.
2. A cycle (`a` inputs `b`, `b` inputs `a`) renders each file once and does not hang.
3. Typing `\section{New}` makes "New" appear within half a second.
4. Clicking an entry in another file opens it at the right line.
5. Moving the cursor into a subsection highlights that row.
6. A commented `% \section{Old}` does not appear.

## 8. Test plan
- **Vitest:** `parseStructure` table tests (levels, stars, short titles, braces, comments, verbatim, `\import`);
  `resolveIncludes` (relative paths, missing file, cycle); outline component: click opens, current row, keyboard,
  empty state.
- **Budget:** pure functions, no slow test.

## 9. Rules and guarantees
| Rule | Guarantee |
|---|---|
| Comments and verbatim never produce entries | `parse-structure.test.ts` |
| Includes are followed once, cycles cut | `resolve-includes.test.ts` |
| The current section is marked for assistive tech | `outline-panel.test.tsx` |

## 10. Definition of Done
- [ ] §5 implemented, §7 passes, §8 green, `make web-test` and `make web-budget` pass.
- [ ] `docs/system/frontend.md` describes the project index and the outline.
- [ ] Glossary: "Outline" → `OutlinePanel` → "Estrutura"; "Project index" → `project-index` → "—".
