# Spec 113 — Spell checking (requirements)

## 1. Summary
Inkstave does not mark typos. This spec checks the words of the visible text against a Hunspell dictionary loaded
in a Web Worker, draws a wavy underline on unknown words, and offers suggestions, "Add to dictionary" and
"Ignore in this document" from a context menu. The text never leaves the browser.

## 2. Context & dependencies
- **Depends on:** 18 (editor), 59 (`EditorPreferences`, settings page).
- **Affected areas:** frontend `editor`, `settings`; backend `auth` (preferences, personal dictionary); docs.
- **New dependencies:** `nspell` (MIT, Hunspell in JS) and dictionary data for `en-US` and `pt-BR`. Check each
  dictionary's licence before adding it (Hunspell dictionaries are often LGPL/MPL/GPL): ship them as separate
  static files under `frontend/public/dictionaries/`, loaded at runtime, never bundled into the MIT code, and list
  them with their licence in `docs/system/frontend.md`. Record the choice in an ADR.

## 3. Goals
- Language per project, chosen by any member with `DOC_WRITE`, stored on the project: `off`, `en-US`, `pt-BR`.
  Default on project creation: the creator's interface language. (Overleaf keeps it per project too: one paper,
  one language.)
- Only the visible ranges plus a margin of 50 lines are checked; rechecks are debounced (400 ms) after edits.
- Skipped: command names (`\section`), arguments of commands that hold keys or code (`\cite`, `\ref`, `\label`,
  `\input`, `\include`, `\includegraphics`, `\usepackage`, `\documentclass`, `\begin`, `\end`, `\url`, `\href`'s
  first argument, `\eqref`, `\cref`), inline and display math (`$…$`, `$$…$$`, `\(…\)`, `\[…\]`, math
  environments), comments, verbatim-like environments, words with digits, all-caps words of up to 5 letters.
- Words inside `\emph{}`, `\textbf{}`, `\section{}`, `\caption{}`, `\footnote{}` are checked.
- Right-click (long press on a phone) on an underlined word: up to 5 suggestions, "Add to dictionary",
  "Ignore in this document". The native context menu stays for other words.
- Personal dictionary per user, synced to the server, at most 5000 words of at most 64 characters.

## 4. Non-goals
- Grammar checking (LanguageTool or similar).
- Languages beyond the two. The design must allow adding one by dropping a dictionary file and a list entry.
- Spell checking in the agent chat or comments (the browser's native spellcheck is enabled there instead).

## 5. Detailed requirements

### 5.1 Data model
- `projects.spellcheck_language` text, check in (`off`, `en-US`, `pt-BR`), default `en-US` for existing rows.
- `user_dictionary_words (user_id FK cascade, word text, created_at)`, primary key `(user_id, lower(word))`.
- One Alembic migration for both.

### 5.2 Backend / API
- `PATCH /api/v1/projects/{project_id}/settings` with `{"spellcheck_language": "pt-BR"}`, capability `DOC_WRITE`
  (a new small route, so editors can change it; rename stays owner-only). Returns the project.
- `ProjectRead` gains `spellcheck_language`.
- `GET /api/v1/me/dictionary` → `{"words": [...]}`; `POST /api/v1/me/dictionary` `{"word"}` (201, idempotent);
  `DELETE /api/v1/me/dictionary/{word}` (204). Words are trimmed, 1–64 chars, no whitespace; 422 otherwise; 409
  `dictionary_full` over 5000.

### 5.3 Frontend
- `frontend/src/modules/spellcheck/` with a public `index.ts`:
  - `tokenize.ts`: `checkableWords(text, from, to): {from, to, word}[]` implementing §3's skip rules. Pure.
  - `spell.worker.ts`: loads `nspell` with the `.aff`/`.dic` of the language on demand, answers
    `check(words[]) → misspelled[]` and `suggest(word) → string[]`. One worker per tab, reused across documents.
  - `spellcheck-extension.ts`: a `ViewPlugin` that tokenizes the visible ranges, asks the worker, and draws mark
    decorations (`cm-misspelled`, a wavy underline in the danger token colour). Words in the personal dictionary
    and the document's ignore list are never marked. The ignore list lives in `localStorage` per document.
  - `spell-menu.tsx`: the context menu (Radix context menu, already a dependency).
- The language selector sits in the editor bar's menu ("Spelling: English / Português (Brasil) / Off";
  PT: "Ortografia: …").
- Settings page: a "Personal dictionary" section to list and remove words.
- The dictionaries are fetched only when a language is on; a failed load shows a quiet notice in the status line
  and the editor works without underlines.
- Interface strings in `en` and `pt`.

## 6. Overleaf reference (study only — never copy)
- `services/web/frontend/js/features/source-editor/extensions/spelling/` — viewport-limited checking, the worker,
  and the context menu.
- `services/web/frontend/js/features/dictionary/` — the personal dictionary UI.

## 7. Acceptance criteria
1. With `en-US`, typing "teh" underlines it; the menu offers "the"; choosing it replaces the word.
2. `\documentclass{artcle}` and `$\alpha$` are never underlined.
3. "Add to dictionary" removes the underline everywhere for that user, in every project, after a reload too.
4. Switching the project to `pt-BR` re-checks: "metodolgia" is underlined, "metodologia" is not.
5. `off` loads no dictionary file (no network request for it).
6. Typing in a 3000-line document keeps input latency unchanged (checking runs in the worker, viewport only).

## 8. Test plan
- **Vitest:** `tokenize` table tests for every skip rule; the extension with a fake worker (marks, ignore list,
  personal dictionary); the menu; language switch triggers a recheck.
- **Integration:** settings route (editor allowed, viewer 403), dictionary routes (idempotent add, 409 cap, 422).
- **Budget:** the worker and dictionaries never load in unit tests (fake worker).

## 9. Rules and guarantees
| Rule | Guarantee |
|---|---|
| Document text never leaves the browser for spell checking | the worker has no network code; `spell.worker.test.ts` |
| Commands, keys and math are never checked | `tokenize.test.ts` |
| A dictionary load failure never blocks editing | `spellcheck-extension.test.ts` |
| Dictionaries are not in the initial bundle | `make web-budget` |

## 10. Definition of Done
- [ ] §5 implemented, §7 passes, §8 green, budgets hold.
- [ ] ADR for the dictionary licences; `docs/system/frontend.md`, `projects.md`, `auth.md` updated.
- [ ] Glossary: "Spell check" → `spellcheck` → "Ortografia"; "Personal dictionary" → `user_dictionary_words` →
      "Dicionário pessoal".
