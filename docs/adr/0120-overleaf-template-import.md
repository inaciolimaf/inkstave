# ADR 0120 — Overleaf templates come in as a zip the user downloads

**Status:** accepted · **Spec:** 120

## Decision

Inkstave never fetches from overleaf.com. The user opens a template on Overleaf, downloads its source
zip (Menu, Download, Source) and uploads it. The import reuses the zip import of spec 101 with
`source=overleaf_template`, which adds three things: the fixes that Overleaf zips need, a compatibility
report, and a first compile.

The compatibility rules are data in `infra/tectonic/compat-rules.toml`, not code. The import job reaches
the first-compile hook through the ARQ `ctx`, so the projects module never imports the compile module.

## Why

Overleaf's gallery offers no source link. Its terms forbid automated access, and "Open as Template" needs
an account. A fetch by URL would break the terms, so the user carries the file.

Rules as data mean a new construct can be flagged without a release. A bad rule stops the worker at
startup, naming the rule.

The job cannot import the compile module: `projects` sits below `compile` in the module order, and the
architecture test only lets the list of exceptions shrink.

## Consequences

- An Overleaf template with a `minted` package or a `latexmkrc` imports, but the report says what may not
  work. Nothing is converted automatically.
- Whether Tectonic renders an EPS figure is not verified against the real engine in CI. The `eps_figure`
  rule asks the user to check the preview.
- The fixes apply only to template imports, so a plain zip behaves as before, except that EPS figures are
  kept for every import.
