# Spec 120 — Start from an Overleaf template (requirements)

## 1. Summary
Most journal and thesis templates live in Overleaf's gallery. The gallery offers no source archive link, only "Open
as Template", which needs an Overleaf account. Its Acceptable Use Policy also forbids scripts and scraping. So Inkstave
does not fetch from it. The user downloads the zip from Overleaf (open the template → Menu → Download → Source) and
uploads it. This spec turns that into a first-class flow on top of the spec 101 import. It fixes the import gaps that
Overleaf templates hit (EPS figures, case clashes, reserved names). After import, it reports which constructs Tectonic
may not handle and runs a first compile.

## 2. Context & dependencies
- **Depends on:** 101 (zip import job), 22 (compile), 109 (dashboard).
- **Affected areas:** backend `projects/transfer`, `compile` (read-only use); frontend `projects`; config; docs.

## 3. Goals
- Dashboard "New project" menu gains **From an Overleaf template…** (PT "De um template do Overleaf…").
- The dialog shows three illustrated steps (text plus a small static diagram, no Overleaf logos or screenshots) and
  a link that opens `https://www.overleaf.com/latex/templates` in a new tab for the user to browse. Then a drop zone for
  the `.zip`.
- Import uses `POST /projects/import` with `source=overleaf_template`; the project name defaults to the template's
  `\title{}` when found, else the zip stem.
- Overleaf-specific fixes in the import:
  - `.eps` figures are kept (they are skipped today: `docs/system/projects.md`, points of attention);
  - a case-only clash between two text entries keeps the first and renames the second `name (2).ext` instead of ending
    `error`;
  - a reserved device name (`con.tex`) is renamed (`con_.tex`), not treated as zip slip, when it is not a traversal;
  - `latexmkrc`/`.latexmkrc` are kept as files and reported (Inkstave does not run latexmk).
- After the import, a **compatibility report**, stored on the import row, lists findings with file and line, and a first
  compile is enqueued.
- The editor shows the report once on first open (a dismissible notice in the status line: "3 things may not work in
  Inkstave"), also reachable from the project menu.

## 4. Non-goals
- Fetching from overleaf.com in any way, including by URL.
- An Inkstave template gallery or "save as template".
- Converting pdfLaTeX-only code automatically.

## 5. Detailed requirements

### 5.1 Data model (one migration)
- `project_imports.source` text, check `zip`/`overleaf_template`, default `zip`.
- `project_imports.compat_report` JSONB nullable: `[{rule_id, severity: "info"|"warning", path, line, message}]`.
- `project_imports.report_seen_at` timestamptz nullable.

### 5.2 Compatibility rules — `infra/tectonic/compat-rules.toml`
An editable file, loaded once per process like the package config. Each rule:
`id`, `severity`, `pattern` (a Python regex over one line, comments stripped), `applies_to` (`tex`, `bib`, `any`
or a file name), `message` (English, the UI translates by `id` when a key exists).

Initial rules (the implementer must verify each against the real Tectonic in `infra/` and drop any that does not apply):

| id | Finds | Why |
|---|---|---|
| `shell_escape` | `\usepackage{minted}`, `pythontex`, `\write18`, `svg` package | needs shell escape, which the sandbox does not allow |
| `latexmkrc` | a `latexmkrc` file | custom build steps are ignored |
| `pdftex_primitive` | `\pdfoutput`, `\pdfminorversion`, `\pdfcompresslevel` | pdfTeX primitives |
| `biber_backend` | `backend=biber` in biblatex options | check bibliography processing in Tectonic |
| `eps_figure` | `\includegraphics{….eps}` | EPS needs conversion; confirm it renders |
| `missing_file` | `\input`/`\include`/`\includegraphics` targets not in the archive | the zip was incomplete |

`scan_compat(entries) -> list[Finding]` is pure and unit tested with fixtures. It runs in the import job after
`reconstruct_tree`, bounded by the existing entry caps.

### 5.3 API
- `POST /projects/import` accepts a form field `source` (`zip` default, `overleaf_template`). Unknown → 422.
- `ProjectImportRead` gains `source`, `compat_report`, `report_seen_at`.
- `POST /projects/{id}/import/{import_id}/report-seen` (`PROJECT_READ`), 204.
- The first compile is enqueued through the compile module's public interface after the import commits, as the
  requester, only when `source = overleaf_template` and status is `success` or `partial`. Its failure does not change
  the import status.

### 5.4 Frontend
- `frontend/src/modules/projects/overleaf-template-dialog.tsx`: steps, external link (`rel="noopener noreferrer"`),
  drop zone reusing the import dialog's upload and SSE status code, then "Open project".
- `frontend/src/modules/editor/compat-notice.tsx`: notice and a list dialog grouped by severity, each finding a link that
  opens the file at the line.
- Strings in `en` and `pt`. Fits 390 px.

## 6. Overleaf reference (study only — never copy)
- `services/web/app/src/Features/Uploads/ProjectUploadManager.mjs` — how Overleaf itself picks the root doc and handles
  zip quirks.
- Do not copy template content into the repository. The test fixtures are small zips written for Inkstave that mimic an
  Overleaf export's layout.

## 7. Acceptance criteria
1. A zip shaped like an Overleaf export with `main.tex`, `figures/plot.eps`, `refs.bib` and `latexmkrc` imports as
   `success`, keeps the EPS, and its report lists `latexmkrc` and `eps_figure`.
2. A zip with `Intro.tex` and `intro.tex` imports both, the second renamed.
3. A template using `minted` reports `shell_escape` at the right line.
4. The project opens with the notice; dismissing it sets `report_seen_at`, and it does not return.
5. A first compile has started when the user opens the project.
6. No request from the backend goes to overleaf.com (assert no HTTP client is used in the import path).

## 8. Test plan
- **Unit:** `scan_compat` with rule fixtures; rule file loading and validation (bad regex → startup error naming the
  rule); renaming helpers for case clash and reserved names.
- **Integration:** import job with the fixture zips (fake enqueuer, `COMPILE_MODE=mock`), report stored, first compile
  enqueued only for templates, `report-seen` route.
- **Vitest:** dialog steps and upload; notice and list; link to file and line.
- **Budget:** fixtures under 50 KB; no real Tectonic.

## 9. Rules and guarantees
| Rule | Guarantee |
|---|---|
| Inkstave never contacts overleaf.com | `test_template_import_makes_no_http_request` |
| EPS figures survive import | `test_overleaf_zip_keeps_eps` |
| A case clash no longer fails the whole import | `test_case_clash_renames_second` |
| Compat rules are data, not code | `infra/tectonic/compat-rules.toml` + `test_compat_rules_load` |

## 10. Definition of Done
- [ ] §5 implemented, §7 passes, §8 green.
- [ ] `docs/system/projects.md` updated, and the EPS, case-clash and reserved-name points of attention resolved there;
      `docs/user-guide.md` explains how to download the zip from Overleaf.
- [ ] Glossary: "Overleaf template import" → `source=overleaf_template` → "Template do Overleaf"; "Compatibility report"
      → `compat_report` → "Relatório de compatibilidade".
