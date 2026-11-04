# Spec 114 — Symbol palette, table builder and visual equation editor (requirements)

## 1. Summary
Symbols, tables and equations are the most typed and least memorable LaTeX. This spec adds an **Insert** menu to
the editor bar with three tools. All three only insert or replace text through a normal editor transaction, so
undo, collaboration and history work unchanged. All three are frontend only.

## 2. Context & dependencies
- **Depends on:** 18 (editor), 106 (tokens), 107 (bar and its menu).
- **Affected areas:** frontend `editor` and a new module `insert-tools`; docs.
- **New dependency:** `mathlive` (MIT) for the equation editor, loaded only when the editor opens. Check the
  version is at least two weeks old and its licence, and record the choice in an ADR.

## 3. Goals
- Symbol palette: about 300 symbols in categories (Greek, relations, operators, arrows, set and logic, delimiters,
  accents, misc), searchable by name or command, inserting the command at the cursor.
- Table builder: rows × columns grid with editable cells, per-column alignment, header row, borders style, caption
  and label; pasting tab-separated text (Excel, Sheets, LibreOffice) fills the grid; produces `table` +
  `tabular` code at the cursor.
- Equation editor: on math under the cursor (or empty), opens a dialog with MathLive showing it visually; Save
  replaces the original LaTeX; Cancel changes nothing.

## 4. Non-goals
- Editing an existing table visually (round-tripping arbitrary `tabular` is unreliable). The builder only creates.
- Drawing TikZ, handwriting recognition.
- Rendering math previews on hover in the editor.

## 5. Detailed requirements

### 5.1 Insert menu
- A button "Insert" (PT "Inserir") in the editor bar, icon-only below 1024 px, opening a menu: Symbol…, Table…,
  Equation…. Disabled for viewers (`isReadOnly`).
- Shortcuts: `Ctrl/Cmd+Shift+Y` symbols, `Ctrl/Cmd+Shift+E` equation. Check they do not clash with the Vim and
  Emacs keymaps; if they do, Vim/Emacs win and the menu still works.

### 5.2 Symbol palette — `frontend/src/modules/insert-tools/symbols/`
- `symbols.json`: `{command, unicode, category, keywords[], package?}`, written for Inkstave. `unicode` is the
  glyph shown in the grid, so no math rendering is needed. A Vitest checks commands are unique and every
  category is known.
- A popover (desktop) or bottom sheet (phone) with a search field focused on open, category tabs, a grid of
  buttons (≥ 44 px on touch), each with `aria-label` = the command and a tooltip with the package.
- Choosing inserts `\command` (with `{}` and the cursor inside for commands that take an argument, flagged in the
  data). When the symbol needs a package the document does not load (`\usepackage{amssymb}` absent from the
  main document), a one-line hint shows "Needs \usepackage{amssymb}" with an "Add it" button that inserts the line
  before `\begin{document}`.
- Recently used symbols (up to 16) first, kept in `localStorage`.

### 5.3 Table builder — `frontend/src/modules/insert-tools/table/`
- Dialog with a grid, start 3 × 3, up to 30 × 15. Add/remove row and column; Tab moves between cells.
- Options: alignment per column (l, c, r, and `p{width}`), header row on/off, style **booktabs**
  (`\toprule`/`\midrule`/`\bottomrule`, adds the package hint like the palette) or **grid** (`|` and `\hline`), caption,
  label (pre-filled `tab:` + caption slug), float placement (`htbp`).
- Paste: when the clipboard has tab or newline separated text, it fills the grid from the focused cell, growing it.
- `to-latex.ts`: pure `tableToLatex(model): string`. Cell text is escaped (`& % $ # _ { } ~ ^ \`) unless the user
  ticks "Cells contain LaTeX" (PT "As células contêm LaTeX"). There is no formula language.
- A live code preview under the grid (monospace, read-only).

### 5.4 Equation editor — `frontend/src/modules/insert-tools/equation/`
- `find-math.ts`: pure `mathAt(text, offset): {from, to, latex, delimiters} | null` for `$…$`, `\(…\)`, `\[…\]`,
  `$$…$$` and the bodies of `equation`, `equation*`, `align`, `align*`, `gather`, `multline` (also with `*`).
  Escaped `\$` is not a delimiter.
- The dialog loads `mathlive` with a dynamic `import()`. While it loads, a spinner; on failure, a plain textarea with
  the LaTeX (the tool degrades, it never blocks).
- Inside a math region: open with its body; Save replaces only the body, keeping the delimiters. Outside: open empty;
  Save inserts `\( … \)` for inline or `\begin{equation} … \end{equation}` for display (a toggle in the dialog).
- MathLive's virtual keyboard is on for touch devices, off by default on desktop with a toggle.
- The MathLive chunk must not enter the initial bundle; `make web-budget` guards it.

### 5.5 Strings
All in `en` and `pt` (`editor` namespace or a new `insert` namespace registered in `frontend/src/i18n`).

## 6. Overleaf reference (study only — never copy)
- `services/web/frontend/js/features/symbol-palette/` — palette layout, search and categories. Do not copy its
  symbol data.
- `services/web/frontend/js/features/source-editor/components/table-generator/` — the table generator flow.
  Overleaf edits tables visually in its rich text mode; Inkstave only builds new ones.
- Overleaf has no MathLive equation editor; the equation dialog has no equivalent.

## 7. Acceptance criteria
1. Searching "alpha" in the palette and choosing it inserts `\alpha` at the cursor.
2. Choosing `\mathbb` inserts `\mathbb{}` with the cursor inside, and offers to add `amssymb` when missing.
3. Pasting a 4 × 3 block from a spreadsheet fills the grid, and Insert yields a compilable `table` with booktabs.
4. A cell with `50%` becomes `50\%`.
5. With the cursor inside `$\frac{a}{b}$`, the equation editor opens showing the fraction; Save after editing
   writes `$\frac{a}{c}$` and keeps the `$`.
6. One Undo after any tool restores the previous text.
7. A viewer cannot open the menu.

## 8. Test plan
- **Vitest:** `symbols.json` integrity; palette search and insert; package hint; `tableToLatex` table tests
  (escaping, booktabs, grid, `p{}` columns, caption/label); paste parsing; `mathAt` table tests (all delimiters,
  escaped `\$`, nested braces); the equation dialog with MathLive mocked, including the load-failure fallback.
- **Budget:** MathLive is never loaded in tests (mocked module).

## 9. Rules and guarantees
| Rule | Guarantee |
|---|---|
| Each tool is one undoable edit | `insert-tools.test.tsx` |
| Cell text is escaped unless marked as LaTeX | `to-latex.test.ts` |
| The equation editor replaces only the math body | `find-math.test.ts`, `equation-dialog.test.tsx` |
| MathLive is not in the initial bundle | `make web-budget` |

## 10. Definition of Done
- [ ] §5 implemented, §7 passes, §8 green, budgets hold, axe clean on the three dialogs.
- [ ] ADR for MathLive; `docs/system/frontend.md` updated.
- [ ] Glossary: "Symbol palette" → `SymbolPalette` → "Símbolos"; "Table builder" → `TableBuilder` →
      "Gerador de tabela"; "Equation editor" → `EquationDialog` → "Editor de equação".
