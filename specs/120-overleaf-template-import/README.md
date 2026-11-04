# Spec 120 — Start from an Overleaf template (prompt)

Let a user start a project from a template they downloaded from Overleaf: a guided "New from Overleaf template"
flow that explains how to get the zip, imports it with the spec 101 machinery, fixes what Overleaf zips commonly
trip on, and reports what may not compile under Tectonic. Inkstave never fetches anything from overleaf.com: the
gallery has no download link and its terms forbid automated access. Read `spec.md`, then implement it with its
tests.

Depends on 101 and 109. Read `docs/system/projects.md` (zip import) and `docs/system/compile.md` first.
