# ADR 0027 — LaTeX log parsing rules & severity mapping

- **Status:** Accepted
- **Date:** 2026-06-09
- **Context spec:** 27 — Compile error & warning annotations

## Context

Tectonic's `output.log` (stored by spec 23) is raw LaTeX engine output. Spec 27
turns it into structured `Problem` records shown in a problems panel and as inline
CodeMirror diagnostics. Overleaf parses logs client-side in TypeScript; Inkstave
parses **server-side in Python** and ships structured JSON. The parsing *rules*
are the public LaTeX-log conventions; the implementation
(`backend/src/inkstave/logparse/latex_log_parser.py`) is independent (no Overleaf
code).

## Decisions

### 1. Line-oriented state machine, total over content

`parse_latex_log(text, *, root_file=None, wrap_width=79)` is a pure function that
**never raises on content** (only on a non-`str` input). Unknown lines are
ignored. The rules:

- **De-wrap.** TeX hard-wraps every log line at `\max_print_line` (~79 cols), so a
  physical line of *exactly* `wrap_width` chars is a continuation. We rejoin such
  runs into **logical lines** before tokenising (criterion 4). `wrap_width<=0`
  disables de-wrapping.
- **File stack.** `(` directly followed by a path-like token (`(<path>.<ext>`)
  opens a file; `)` closes one. A `(` *not* followed by a path pushes a balancing
  **sentinel** so stray parens in prose don't pop a real file. The current file is
  the top-most real path, falling back to `root_file` (which seeds unattributed
  early messages to the main document). Paths are normalised (strip `./`, collapse
  `..`); bundled system paths are kept verbatim and simply won't match an editor doc.
- **Errors** (`severity=error`, `rule="tex-error"`): a `! …` line starts a TeX
  error; the message is its first line and the line number comes from a following
  `l.<n>` marker (scanned up to 25 lines, stopping at a blank line or the next
  `!`). The `<file>:<line>: <message>` (file:line:error) form some packages emit is
  also recognised, carrying its own file + line.
- **Warnings** (`severity=warning`): `LaTeX Warning:`, `Package/Class X Warning:`
  (`rule="package-warning"`/`"class-warning"`), `LaTeX Font Warning:`
  (`"font-warning"`). `(name)`-prefixed continuation lines are folded into the
  message; a trailing `on input line <n>.` sets the line. An undefined
  `Reference …`/`Citation …` retags the rule to `"undefined-ref"`/`"undefined-cite"`.
- **Typesetting** (`severity=info`): `Overfull/Underfull \hbox|\vbox` →
  `rule="overfull-hbox"` etc., with `at lines a--b` → `line`+`end_line` or
  `detected at line n`/`at line n` → `line`.

### 2. Severity mapping

`error` for TeX errors; `warning` for the LaTeX/package/class/font warning
families; `info` for typesetting boxes and recoverable notices. The frontend maps
these 1:1 to CodeMirror `@codemirror/lint` severities (`error`/`warning`/`info`),
so colour is never the only signal — the panel also shows an icon + text.

### 3. Service-level guards (config, not parser)

`LogProblemsService` resolves the compile (`"latest"`/`None` → most recent),
reads `output.log`, and **tail-truncates** to `LOGPARSE_MAX_LOG_BYTES` (8 MiB)
before parsing (a synthetic `info` "log-truncated" problem is prepended); the
parse runs in a worker thread. The result is capped at `LOGPARSE_MAX_PROBLEMS`
(1000) with a synthetic `info` "N more problems omitted". `LOGPARSE_WRAP_WIDTH`
(79) is the de-wrap width.

### 4. Endpoint, errors & authz

`GET /api/v1/projects/{id}/compiles/{compile_id}/problems` (and the `…/latest/…`
alias via the same route) returns `CompileProblems` with per-severity counts.
`LogNotAvailable` → `404` `log_unavailable`. Reuses the Phase-2 project-access
dependency, which returns **404 (not 403)** for a non-member by deliberate
anti-enumeration design (ADR 0007).

**Not folded into the compile-status stream.** The spec allows folding the
`{errors,warnings,infos}` summary into the compile-result payload "if one is
exposed". We deliberately **do not**: the status payload is polled/streamed
frequently and computing counts means parsing the stored log on every poll. The
UI badges from this dedicated endpoint instead (one fetch per finished compile).

## Consequences

- New backend module `backend/src/inkstave/logparse/` (parser, service, router);
  one read-only endpoint. No DB tables; parsing is on demand.
- Frontend: a typed `problems` client, `useProblems`, a `ProblemsPanel` (grouped,
  click-to-jump, reusing the spec-26 editor reveal), and `@codemirror/lint`
  inline diagnostics for the open file that refresh on each compile.
- Three new env vars (`LOGPARSE_MAX_LOG_BYTES`, `LOGPARSE_WRAP_WIDTH`,
  `LOGPARSE_MAX_PROBLEMS`) in `.env.example`. New dep: `@codemirror/lint`.
- Tests use checked-in fixture logs — no compile; suite stays well under 2 minutes.
