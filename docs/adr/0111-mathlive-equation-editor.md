# ADR 0111 — MathLive is the visual equation editor, loaded on demand

**Status:** accepted · **Spec:** 114 — Symbol palette, table builder and visual equation editor

## Decision

The equation dialog edits formulas with `mathlive` 0.111.1 (MIT). The library is loaded with a dynamic
`import()` the first time the dialog opens, together with its font stylesheet. Its fonts come from the
Vite build, not from a folder the server has to serve. If the load fails, the dialog shows a plain textarea
with the LaTeX, so the tool degrades and never blocks the document.

## Why MathLive

- The equation editor must show the formula visually and write LaTeX back. MathLive does both and is
  maintained. KaTeX only renders, so it cannot edit. MathQuill is unmaintained, and the TipTap math
  extensions need a rich-text editor that Inkstave does not use.
- MIT is compatible with Inkstave's licence, and the library is small enough to load lazily.
- Its virtual keyboard fits touch devices, which the editor has to support (spec 107).

## Version

The rule for a new dependency is a release at least two weeks old. On 2026-11-04 that means 0.111.1
(released 2026-10-09). 0.111.2 to 0.111.4 came out on 2026-10-31 and are too recent. Upgrades follow the
same rule, and the lock file pins the exact version.

## Consequences

- The MathLive chunk and its KaTeX fonts stay out of the initial bundle. `make web-budget` gates the initial
  JavaScript at 250 KB gzip, and it measured 191 KB after this change. The chunk is loaded only when a
  person opens the equation editor, so the first open pays for it.
- MathLive's own sounds are turned off, since they are not part of the editor's design.
- Tests never load MathLive. The loader module is mocked, and the fallback path is tested by making the
  mock fail.
- Hover previews of math in the editor are out of scope, as spec 114 says. The editor does not render math
  outside the dialog.
