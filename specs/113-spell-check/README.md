# Spec 113 — Spell checking (prompt)

Underline misspelled words in the editor, with suggestions, in English and Brazilian Portuguese, without
sending the text anywhere: Hunspell dictionaries run in a Web Worker in the browser, LaTeX commands and math
are skipped, and each user has a personal dictionary. Read `spec.md`, then implement it with its tests.

Depends on 18 and 59 (preferences). Read `docs/system/frontend.md` and `docs/system/auth.md` first.
