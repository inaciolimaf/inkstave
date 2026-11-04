# ADR 0113 — Spell checking runs in the browser, with Hunspell dictionaries as static files

**Status:** accepted · **Spec:** 113

## Decision

Spell checking runs in a Web Worker in the browser. The engine is `nspell` 2.1.5 (MIT), which reads Hunspell
`.aff`/`.dic` pairs. The dictionaries are static files in `frontend/public/dictionaries/`, fetched only when a
project's language is on, and they are never bundled into the application's code. They are copied from the pinned
npm packages at build time and gzipped, so the repository holds no dictionary data.

Two dictionaries ship, from the `wooorm/dictionaries` packages on npm, which take them from their upstream projects:

| Language | Package | Upstream | Licence, as the package states it | Used under |
|---|---|---|---|---|
| `en-US` | `dictionary-en` 4.0.0 | SCOWL (Spell Checker Oriented Word Lists) | `(MIT AND BSD)`; the notice is kept as `en-US.LICENSE.txt` | MIT and BSD, unmodified |
| `pt-BR` | `dictionary-pt` 4.0.0 | LibreOffice VERO, Brazilian Portuguese | `(LGPL-3.0 OR MPL-2.0)`; the notice is kept as `pt-BR.LICENSE.txt` | MPL-2.0, unmodified |

Both packages were published in 2023, well over two weeks before this change. `dictionary-pt-br` 3.0.0 is
deprecated upstream in favour of `dictionary-pt`, so it is not used.

## Why this design

**Text never leaves the browser.** A spell checker that calls a server would send every paragraph of a thesis to
it. A worker with no network code, and a dictionary fetch that carries no document text, keep the check local.
`frontend/src/modules/spellcheck/spell-engine.test.ts` checks that the worker sources hold no other network API.

**Dictionaries are separate files, not bundled.** LGPL and MPL material must not be merged into MIT code without
care. As unmodified files beside the app, each keeps its own licence and notice. Adding a language means dropping
its files there and adding one list entry.

**Only the dictionaries of the chosen language are loaded.** The default `off` loads nothing, and the first check
of a language starts its download. A failed download is forgotten, so the next request retries.

**Why not LanguageTool or a server service.** Grammar checking is a non-goal, and any service would receive the text.

## Consequences

- Licence notices travel with the dictionaries (`public/dictionaries/*.LICENSE.txt`). A change of dictionary needs
  a new check of its licence in this ADR.
- The LGPL and MPL options of `dictionary-pt` both allow use with an MIT application. Choosing MPL-2.0 means the
  files are used unmodified; a modified copy would have to publish its changes under MPL-2.0.
- Measured at build time: the Portuguese `.dic` is 4.5 MB raw and 1.3 MB gzipped (the `.aff` is 0.1 MB gzipped); the
  English `.dic` is 0.55 MB raw and 0.19 MB gzipped. They are loaded on demand, and they are outside the initial
  JavaScript budget, which `make web-budget` checks.
- The spelling language is stored per project, so one paper has one language, as Overleaf also does.

## Deviation recorded here

The spec asked for a personal-dictionary key of `(user_id, lower(word))` as the primary key. PostgreSQL primary
keys take columns, not expressions. `user_dictionary_words` therefore has the same rule as a unique index
`uq_user_dictionary_words_user_lower_word` on `(user_id, lower(word))`. The table is a Core table, not an ORM
class, because it has no primary key for the ORM to map.

## Not measured

The acceptance criterion about input latency in a 3000-line document was not measured in a browser. The design
keeps the work off the main thread (the worker answers the check), limits it to the visible lines plus 50, and
runs it 400 ms after the last edit, but the figure itself is not recorded.
