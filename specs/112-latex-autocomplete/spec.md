# Spec 112 — LaTeX autocomplete (requirements)

## 1. Summary
Without completion a writer must remember every command, label and citation key. This spec adds
`@codemirror/autocomplete` with five sources fed by static data and by the project index of spec 111.

## 2. Context & dependencies
- **Depends on:** 18 (editor), 111 (project index: labels, files, live parse).
- **Affected areas:** frontend `editor`, `project-index`; docs. New dependency `@codemirror/autocomplete` (part of
  the approved CodeMirror 6 stack).

## 3. Goals
| Trigger | Source | Shows |
|---|---|---|
| `\` + letters | commands | name, a one-line hint, the package it needs if not core |
| `\begin{` + letters | environments | name; choosing inserts `\begin{x}…\end{x}` with the cursor inside |
| `\cite{`, `\citep{`, `\citet{`, `\parencite{`, `\textcite{`, `\autocite{`, `\nocite{`, after a comma inside them | bib keys | key, title, first author, year |
| `\ref{`, `\eqref{`, `\autoref{`, `\cref{`, `\Cref{`, `\pageref{`, `\nameref{` | labels | label, the file and the enclosing section title |
| `\input{`, `\include{`, `\subfile{`, `\includegraphics{`, `\bibliography{`, `\addbibresource{` | project files | paths filtered by the right extensions |
| `\usepackage{`, `\RequirePackage{`, after a comma inside them | packages | name |

- Snippets use CodeMirror snippet fields: `\frac{${num}}{${den}}`, Tab jumps fields, Escape leaves them.
- Fuzzy prefix matching (CodeMirror's default), most relevant first: exact prefix, then recently used in this
  document, then alphabetical.
- Completion never fires inside a comment or verbatim environment.

## 4. Non-goals
- AI completion of prose (competitors' "copilot", item 22 of the research: not chosen).
- Validating that a command exists or a label resolves (the compile log does that).
- Parsing `.bib` on the server.

## 5. Detailed requirements

### 5.1 Static data — `frontend/src/modules/editor/completion/data/`
- `commands.json`: about 400 entries `{name, snippet?, hint, package?}` covering core LaTeX, `amsmath`,
  `amssymb`, `graphicx`, `hyperref`, `biblatex`/`natbib`, `booktabs`, `xcolor`, `tikz` basics. Written by hand for
  Inkstave; do not import Overleaf's lists (AGPL).
- `environments.json`: about 60 entries with body snippets (`figure` with `\centering`, `\includegraphics`,
  `\caption`, `\label`; `table`, `tabular` with a column spec field, `itemize` with `\item`, `align`, `equation`,
  `frame`…).
- `packages.json`: package names. Prefer generating it from `infra/tectonic/packages.toml` plus a curated list,
  with a script in `scripts/` and a Vitest that the JSON is sorted and unique.
- Data files are loaded lazily the first time completion opens (dynamic `import()`), so the initial bundle stays
  under `make web-budget`.

### 5.2 Bibliography — `frontend/src/modules/project-index/parse-bib.ts`
- `parseBib(text): BibEntry[]` with `{key, type, title?, author?, year?}`. Tolerant: `@comment`, `@string`,
  `@preamble` skipped; braces and quotes as delimiters; an unparseable entry is skipped, never throws.
- The project index (spec 111) adds every `.bib` document of the project. A key appears once even if two files
  define it (first wins, a hint "also in other.bib").
- Titles strip one outer brace level and LaTeX accents are shown as typed.

### 5.3 Editor wiring
- `completion/sources/*.ts`, one file per source, each a `CompletionSource` that reads the context with a small
  regex on the current line (the LaTeX language is a `StreamLanguage`, so there is no syntax tree to query).
- `completion/extension.ts` returns the `autocompletion({override: [...]})` extension. It is added in
  `codemirror-extensions.ts`, behind a new editor preference `autocomplete: boolean` (default `true`) in
  `EditorPreferences` (backend schema, frontend settings section "Autocomplete" / "Autocompletar").
- Keyboard: Ctrl+Space opens; Enter or Tab accepts; the Vim keymap keeps working (accept in insert mode only).
- The completion popup uses the theme tokens of spec 106 in both themes.

## 6. Overleaf reference (study only — never copy)
- `services/web/frontend/js/features/source-editor/languages/latex/complete.ts` and its `completions/` folder —
  how sources are split by context. Do not copy the data lists.
- `services/web/frontend/js/features/source-editor/languages/latex/completions/doc-commands.ts` — idea of
  completing commands the user defined (out of scope here, but keep the source pluggable).

## 7. Acceptance criteria
1. Typing `\sec` offers `\section{}` and choosing it puts the cursor between the braces.
2. `\begin{fig` + Enter yields a complete `figure` block with fields.
3. With `refs.bib` holding `@article{silva2023, title={Deep}, author={Silva, A.}, year={2023}}`, typing `\cite{si`
   offers `silva2023 — Deep — Silva, 2023`; after `\cite{silva2023, ` it offers keys again.
4. A `\label{fig:plot}` in another file is offered after `\ref{fig`.
5. `\includegraphics{` offers only image files of the project.
6. Inside `% \sec` nothing pops up.
7. Turning the preference off removes the popup; the setting survives a reload.

## 8. Test plan
- **Vitest:** each source with an `EditorState` fixture and `CompletionContext`; `parseBib` table tests including
  malformed input; data files sorted and unique; preference toggle.
- **Integration (pytest):** `EditorPreferences` accepts and returns `autocomplete`.
- **Budget:** pure, fast.

## 9. Rules and guarantees
| Rule | Guarantee |
|---|---|
| Completion never fires in comments or verbatim | `context.test.ts` |
| A malformed `.bib` never breaks completion | `parse-bib.test.ts` |
| Completion data is not in the initial bundle | `make web-budget` |

## 10. Definition of Done
- [ ] §5 implemented, §7 passes, §8 green, budgets hold.
- [ ] `docs/system/frontend.md` updated; `docs/system/auth.md` lists the new preference field.
- [ ] Glossary: "Autocomplete" → `completion` → "Autocompletar".
