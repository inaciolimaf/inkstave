# Originality / License Audit (spec 60)

**Result: PASS.** Inkstave shares **no code** with Overleaf. It is an independent,
MIT-licensed implementation; the Overleaf Community Edition repo was used only as
*study material* under the rule in [CLAUDE.md](../CLAUDE.md) and
[CONTRIBUTING.md](../CONTRIBUTING.md). This audit is reproducible — every check and
its result is below.

## Why the code is necessarily independent

Inkstave's stack does not overlap with Overleaf's, so line-level reuse is not even
mechanically possible:

| Concern | Inkstave | Overleaf CE |
| --- | --- | --- |
| Backend | Python · FastAPI · SQLAlchemy (async) | Node.js · Express |
| Database | PostgreSQL | MongoDB |
| Real-time | pycrdt (server) + Yjs (browser), CRDT | ShareJS / OT |
| LaTeX | Tectonic (single binary) | TeX Live + latexmk |
| Jobs | ARQ (Redis) | per-service queues |
| AI agent | LangGraph (no Overleaf equivalent) | — |

A Python/SQLAlchemy/pycrdt codebase cannot contain copied Node/Express/Mongo/ShareJS
source.

## Reproducible checks

Run from the repo root. All returned the expected clean result on the audited tree.

1. **No copied Overleaf identifiers** (its distinctive module names / package scope):

   ```bash
   grep -rin "sharejs\|sharelatex\|DocumentUpdater\|@overleaf" backend/src frontend/src
   # → 0 matches
   ```

2. **References to "overleaf" are study/avoidance comments only** — never code:

   ```bash
   grep -rin "overleaf" backend/src frontend/src
   ```
   5 matches, all comments explicitly asserting independence, e.g.
   `services/safe_path.py` ("Reimplements the *rules* of Overleaf's SafePath
   independently"), `logparse/latex_log_parser.py` ("Overleaf code." — in a "not
   copied from" sentence), `synctex/parser.py`, `config.py`, and
   `frontend/.../latex-language.ts` ("deliberately does **not** use or translate
   Overleaf's …"). None contain copied logic.

3. **No AGPL headers in Inkstave source:**

   ```bash
   grep -rin "AGPL\|Affero" backend/src frontend/src
   ```
   1 match — a comment in `frontend/src/features/editor/latex-language.ts` noting
   that Inkstave's grammar deliberately does **not** use the AGPL `lezer-latex`
   grammar (see [adr/0018-latex-language.md](adr/0018-latex-language.md)). It is an
   avoidance note, not a license header.

4. **License is MIT:**

   ```bash
   head -1 LICENSE        # → "MIT License"
   ```

5. **No Overleaf reference material vendored.** The Overleaf repo lives *outside*
   this repo (cloned at `../overleaf/`, a sibling). Specs cite Overleaf paths in
   their "Overleaf reference (study only)" sections as a reading list; nothing from
   `../overleaf/` is copied into the Inkstave tree.

6. **No secrets committed** (related repo-hygiene check):

   ```bash
   git ls-files | grep -E '(^|/)\.env$'   # → 0 (only .env.example is tracked)
   grep -n '\.env' .gitignore             # → .env and *.env are ignored
   ```

## Conclusion

The audit **passes with no remediations required**: MIT license, no AGPL headers,
no copied Overleaf identifiers or strings, an architecturally disjoint stack, and
no vendored reference material. Inkstave is original work.
