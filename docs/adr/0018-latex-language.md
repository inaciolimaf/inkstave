# ADR 0018 — CodeMirror 6 editor: LaTeX highlighting, theme, read-only baseline

- **Status:** Accepted
- **Date:** 2026-06-09
- **Context spec:** 18 — Editor UI (CodeMirror 6)

## Context

The editor pane renders a selected document in a CodeMirror 6 view with LaTeX
syntax highlighting, line numbers, a theme, and basic settings. It is **read-only**
this spec (editing/autosave arrive in spec 19). A hard constraint: the LaTeX
grammar must be **independently, permissively licensed** — Overleaf's
`lezer-latex` is AGPL and must **not** be copied or translated.

## Decisions

### 1. LaTeX highlighting — self-authored `StreamLanguage` (MIT)

Rather than depend on a third-party LaTeX grammar (availability + license
verification risk), Inkstave ships its **own** small highlighter built on
CodeMirror's `StreamLanguage` (`@codemirror/language`), in
`features/editor/latex-language.ts`. It highlights **commands** (`\foo`,
starred, and escaped symbols), **comments** (`%…`), and **math** (`$…$` / `$$…$$`).
This is original Inkstave code (MIT); it does not use, vendor, or translate
Overleaf's `lezer-latex` grammar. A richer `@lezer`-based grammar can replace it
later behind the same `latex()` `LanguageSupport` factory without touching the
editor. Token colours come from `@codemirror/language`'s `defaultHighlightStyle`
(light) and `@codemirror/theme-one-dark` (dark).

**Licensing:** every editor dependency is permissive — all `@codemirror/*` and
`@lezer/*` packages and `@codemirror/theme-one-dark` are **MIT** (the CodeMirror
project); `react-resizable-panels` is **MIT**; the LaTeX highlighter is our own.

### 2. One `EditorView`, reconfigured via compartments

`CodeMirrorEditor` creates a single `EditorView` on mount and **never recreates
it** on prop changes. Settings/theme live in **compartments**
(`theme`/`font`/`wrap`/`keymap`) reconfigured by `dispatch`; switching documents
replaces the doc via a `changes` transaction. `placeholderData: keepPreviousData`
on the content query keeps the view mounted across doc switches (AC9). Baseline
extensions: `lineNumbers`, active-line + gutter highlight, `bracketMatching`,
`highlightSpecialChars`, `drawSelection`, `history`, and
`syntaxHighlighting(defaultHighlightStyle)`.

### 3. Read-only enforcement

`EditorState.readOnly.of(true)` + `EditorView.editable.of(false)` make the view
non-editable (typing/paste/cut do nothing; caret/selection/copy still work).
Spec 19 flips these through the same configuration. The content region carries
`aria-label="LaTeX editor"` and `aria-readonly="true"`.

### 4. Settings & theme

Settings (`fontSize` 10–24 clamped, `lineWrapping`, `keymap`) persist in
`localStorage` (app-wide). Only the **default** keymap ships this spec
(`defaultKeymap` + `historyKeymap`); vim/emacs are intentionally omitted to avoid
extra dependencies — the settings popover exposes **font size** and **line
wrapping** (the live, user-facing ones). Dark mode follows the `dark` class on
`<html>` (Tailwind convention) via a `MutationObserver`.

### 5. IDE shell

`EditorWorkspace` uses the shadcn **resizable** panels (`react-resizable-panels`,
MIT) for a 3-pane layout (tree | editor | preview placeholder), `autoSaveId`
persisting sizes. On narrow viewports the group switches to a **vertical
(stacked)** direction via `useMediaQuery`.

## Consequences

- New deps (all MIT, pinned): `@codemirror/{state,view,language,commands}`,
  `@lezer/highlight`, `@codemirror/theme-one-dark`, `react-resizable-panels`,
  `@radix-ui/react-popover`, `@radix-ui/react-switch`.
- Spec 19 makes the editor editable + wires autosave using the captured
  `version`; spec 24 fills the preview pane.
- Tests: CM6 runs in jsdom (with small `Range`/`ResizeObserver`/`matchMedia`
  polyfills); the read-only/highlighting/compartment behaviours and the pane
  state-machine are unit/integration-tested; one Playwright flow covers
  open → highlight → read-only → font-size-live.

## Alternatives considered

- **A third-party `codemirror-lang-latex` package** — viable if MIT, but adds a
  dependency whose maintenance/license must be tracked; the self-authored
  StreamLanguage is small, fully owned, and sufficient for commands/comments/math.
- **Overleaf's `lezer-latex`** — **rejected outright** (AGPL; originality rule).
- **Recreating the view per document** — simpler but loses scroll/selection and
  churns the DOM; rejected in favour of compartment reconfiguration.
