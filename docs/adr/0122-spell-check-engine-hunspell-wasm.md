# ADR 0122 — Spell check engine: Hunspell in WebAssembly instead of nspell

**Status:** accepted · **Spec:** 113 · **Supersedes:** the engine choice in ADR 0113 (the rest of it stands)

## Context

ADR 0113 chose `nspell` 2.1.5 to read the Hunspell dictionaries in the browser. In production the Portuguese
check never worked: the status line said "Spell check unavailable: the dictionary did not load". nspell expands
every word with every affix rule while it loads, and the LibreOffice VERO pt-BR dictionary has so many rules that
the build never finished (measured in Node: English in 97 ms; Portuguese still running after 300 s). The client's
15 s deadline then failed the load. The unit tests used a tiny dictionary, so they did not see it.

## Decision

Use `hunspell-asm` 4.0.2: the real Hunspell compiled to WebAssembly, with the binary embedded in its JavaScript.
It loads pt-BR in about 350 ms and en-US in tens of milliseconds, in Node and in the browser worker, and its
suggestions are Hunspell's own.

- Licence: the wrapper is MIT; Hunspell is tri-licensed (MPL-1.1, GPL-2.0, LGPL-2.1) and used under MPL-1.1,
  unmodified.
- It is loaded only by the spell worker (about 740 kB, fetched the first time a project with the check on opens),
  so the initial bundle and its 250 KB budget do not change.
- Its ESM build does `import * as x from "y"` on CommonJS modules that export a function and then calls `x()`.
  A bundle cannot call a namespace ("k is not a function"), so `frontend/vite-plugins/hunspell-interop.ts` rewrites those
  imports, for the production worker bundle (Rollup) and for the dev server's pre-bundling (esbuild).
- A test loads the real pt-BR dictionary files, so a slow or broken engine fails the suite.

## Consequences

- The package was last published in 2022. If it ever breaks, the interop plugin fails loudly at build or load time,
  and the engine sits behind the small `SpellDictionary` interface in `spell-engine.ts`, so a swap touches one
  function.
- The dictionary files, their licences and the worker protocol are unchanged.
