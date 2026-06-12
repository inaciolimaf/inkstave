# Spec 27 — Compile error & warning annotations (requirements)

## 1. Summary

This spec turns the raw LaTeX `output.log` (produced by Tectonic in spec 21,
stored in spec 23) into a structured list of **problems** — errors, warnings and
typesetting issues, each with `file`, `line`, `severity`, `message` and a short
`raw` excerpt. The list is returned from a backend endpoint, shown in a
**problems panel** in the UI (next to/within the spec-24 log panel), and rendered
as **inline CodeMirror 6 diagnostics** at the matching lines in the editor. The
LaTeX log format is public; we write our own parser. Overleaf is consulted only
for the parsing *approach*, not its code.

## 2. Context & dependencies

- **Depends on:**
  - **spec 24** (PDF preview UI + log panel): provides the compile result view,
    the raw-log display, and the place to mount a problems panel; also provides
    the "current compile" concept the frontend already tracks.
  - **spec 18** (CodeMirror 6 editor): provides the editor instance into which we
    push diagnostics via the `@codemirror/lint` extension.
  - Transitively **spec 23** (output storage): the raw `output.log` bytes are
    retrievable by `(project_id, compile_id)` / "latest compile".
- **Unlocks:** better authoring UX; the AI agent (Phase 6) and history specs do
  not depend on it but benefit from structured problems.
- **Affected areas:** backend (`logparse` module + 1 endpoint, optionally fold
  parsing into the spec-22 compile-result payload), frontend (problems panel +
  CodeMirror lint integration), docs (parser ADR).

## 3. Goals

- Parse a LaTeX log into structured `Problem` records covering at least:
  - **errors**: `! …` TeX errors, including the `l.<n>` line marker and
    `<file>:<line>:` style messages;
  - **warnings**: `LaTeX Warning:`, `Package <name> Warning:`,
    `Class <name> Warning:`, and `LaTeX Font Warning:`;
  - **typesetting**: `Overfull`/`Underfull \hbox`/`\vbox` with their line range;
  - **undefined references / citations** as warnings.
- Resolve which **file** a problem belongs to by tracking the log's `(`…`)`
  file-open/close stack, and which **line** from `l.<n>`, `on input line <n>`,
  `lines <a>--<b>`, or `<file>:<line>:` tokens.
- Expose a backend endpoint returning the parsed problems for a compile.
- Frontend: a problems panel (grouped by severity, click-to-jump to the source
  line) and inline CodeMirror diagnostics that appear on the correct lines of the
  open document and update on each compile.
- Be resilient: never raise on weird log content; unknown lines are ignored.

## 4. Non-goals (explicitly out of scope)

- SyncTeX source↔PDF click sync — **spec 26**.
- Running compiles, storing logs, or the PDF viewer — **specs 21–24**.
- BibTeX/`.blg` log parsing as a separate stream (parse only what appears in the
  main `output.log`; a dedicated bib-log parser is out of scope).
- "Human-readable" rewrites / help links for each error type (we surface the raw
  LaTeX message; friendly hints are a later nicety, not this spec).
- Quick-fixes / code actions on diagnostics.

## 5. Detailed requirements

### 5.1 Data model

No new database tables. Parsing is done on demand from the stored log. In-memory
models in `backend/app/logparse/models.py`:

```python
class ProblemSeverity(str, Enum):
    error = "error"
    warning = "warning"
    info = "info"      # typesetting (overfull/underfull), undefined-but-recoverable

class Problem(BaseModel):
    severity: ProblemSeverity
    message: str            # cleaned, single-line summary (rewrapped)
    file: str | None        # project-relative source path, None if unresolved
    line: int | None        # 1-based source line, None if unknown
    end_line: int | None    # for ranges (Overfull "lines a--b"); else None
    raw: str                # the original log excerpt (a few lines) for the panel
    rule: str               # short machine id: "tex-error","latex-warning",
                            #   "package-warning","overfull-hbox","undefined-ref",…

class CompileProblems(BaseModel):
    compile_id: str
    errors: int             # counts by severity for badges
    warnings: int
    infos: int
    problems: list[Problem] # in log order
```

### 5.2 Backend / API

#### 5.2.1 Parser — `backend/app/logparse/latex_log_parser.py`

Independent implementation. The parser is a line-oriented state machine over the
decoded log text (UTF-8 with `errors="replace"`; LaTeX logs are mostly ASCII).
Key rules (document these in `docs/`):

- **File stack.** LaTeX prints `(` immediately followed by a filename when it
  opens a file and `)` when it closes one. Maintain a stack so the "current file"
  is the top of the stack. Parsing the parenthesis stream is the fiddly part:
  - a `(` is a file-open only when directly followed by a path-like token;
  - balance `)` against opens; ignore unbalanced/parenthetical noise gracefully;
  - line wrapping: the log wraps at ~79 columns, so filenames and messages can
    span multiple physical lines — **de-wrap** by joining a continuation line
    when the previous line is exactly the wrap width (configurable, default 79)
    before tokenising. Document the chosen heuristic.
- **Errors.** Lines starting with `! ` begin a TeX error; the message continues
  until a line `l.<n> <context>` which gives the line number, or a blank line.
  Also recognise `<file>:<line>: <message>` (file:line:error) form some packages
  emit.
- **Warnings.** `LaTeX Warning:`, `Package X Warning:`, `Class X Warning:`,
  `LaTeX Font Warning:` — capture the (possibly multi-line) message; a trailing
  `on input line <n>.` sets the line. `Reference … undefined`/`Citation …
  undefined` → `rule="undefined-ref"`/`"undefined-cite"`.
- **Typesetting.** `Overfull \hbox …` / `Underfull \hbox …` / `…\vbox…` with
  `at lines <a>--<b>` or `detected at line <n>` → severity `info`,
  `rule="overfull-hbox"` etc., set `line`/`end_line`.
- **Files.** Resolve `file` to a project-relative path (normalise leading `./`,
  collapse `..`); if the top of the stack is an absolute/system path (e.g. a
  bundled `.sty`), keep it but it will simply not match any open editor doc.

Public contract:

```python
def parse_latex_log(text: str, *, root_file: str | None = None,
                    wrap_width: int = 79) -> list[Problem]:
    """Pure function: log text -> ordered problems. Never raises on content;
    only raises ValueError on a None/non-str input. root_file seeds the file
    stack so unattributed early messages map to the main document."""
```

#### 5.2.2 Service / integration

```python
class LogProblemsService:
    def __init__(self, output_store: OutputStore): ...
    async def problems_for(self, project_id: UUID, compile_id: str | None
                          ) -> CompileProblems:
        """Resolve compile_id (None => latest), fetch output.log bytes, decode,
        parse, count, and return. Raises LogNotAvailable (-> 404) if the compile
        has no output.log."""
```

Parsing runs in a worker thread (`anyio.to_thread.run_sync`) to keep the event
loop free for large logs.

#### 5.2.3 HTTP endpoint — `backend/app/logparse/router.py`

Auth: authenticated project member (same dependency family as spec 26; tighten in
spec 34).

**`GET /api/projects/{project_id}/compiles/{compile_id}/problems`**
(and a convenience alias `…/compiles/latest/problems`).

- `200`: `CompileProblems`.
- `404`: project/compile/log absent → `{"detail":"log_unavailable"}`.
- `401/403`: auth.

Additionally, **fold a summary into the compile-result payload** if spec 22/24
exposes one: include `{errors, warnings, infos}` counts so the UI can badge the
compile button without a second request. The full list still comes from this
endpoint (kept separate to avoid bloating the status stream).

### 5.3 Frontend / UI

- **API client** (`frontend/src/lib/api/problems.ts`): `getProblems(projectId,
  compileId|"latest")` returning typed `CompileProblems`; `404 log_unavailable`
  surfaced as an empty/“no log” state.
- **Problems panel** (`frontend/src/features/compile/ProblemsPanel.tsx`): a tab
  alongside the spec-24 raw-log view.
  - Groups by severity with counts (errors / warnings / typesetting), collapsible
    sections, severity icons (shadcn/ui + lucide). Empty state: "No problems."
  - Each row shows `severity`, `message`, and `file:line` when known. Clicking a
    row with a known `file`/`line` opens that document (reuse the editor open
    flow) and scrolls to the line (reuse spec-26's editor-jump helper if present,
    else a minimal scroll-to-line).
  - Loads on each successful or failed compile; shows the latest compile's
    problems.
- **Inline diagnostics** (`frontend/src/features/editor/diagnostics.ts`): a
  CodeMirror 6 `@codemirror/lint` integration.
  - Maintain a `StateField`/`linter` source fed from the problems of the
    **currently open file** (filter `CompileProblems.problems` by `file ===
    openDocPath`). Map each to a CM `Diagnostic` at the line's range
    (`from = line start, to = line end`, or the `[line,end_line]` range for
    typesetting), `severity` mapped error→`"error"`, warning→`"warning"`,
    info→`"info"`.
  - Diagnostics refresh when a new compile completes; they are cleared when the
    user edits past them only if cheap (otherwise simply replaced on next
    compile — replacement on compile is the required behaviour; live clearing is
    optional).
  - A gutter marker + the standard CM lint underline; hovering shows the message.
- **States:** while a compile is running, keep the previous problems but show a
  "stale" hint; on a fresh result, replace. On `log_unavailable`, panel shows
  "No log yet — run a compile."
- **Accessibility:** problems panel rows are buttons (keyboard navigable) with
  `aria-label` including severity, file and line; diagnostic colours are not the
  only signal (icons + text in the panel).

### 5.4 Real-time / jobs / external integrations

None new. Parsing is synchronous-on-request (thread-offloaded). No ARQ job is
required — the log already exists from the spec-22 compile job. (If a later
optimisation wants to parse once at compile time and cache the result, that is a
spec-22/23 change, not this spec.)

### 5.5 Configuration

- `LOGPARSE_MAX_LOG_BYTES` (default `8388608`, 8 MiB): logs larger than this are
  truncated from the end before parsing (with a synthetic `info` problem noting
  truncation); prevents pathological memory/CPU use.
- `LOGPARSE_WRAP_WIDTH` (default `79`): physical wrap width used for de-wrapping.
- `LOGPARSE_MAX_PROBLEMS` (default `1000`): cap the returned list; append a
  synthetic `info` "N more problems omitted" if exceeded.
- No secrets. Add all three to `.env.example` with comments.

## 6. Overleaf reference (study only — never copy)

> Read these in `../overleaf/` to understand the approach, then write your own.

- `services/web/frontend/js/ide/log-parser/latex-log-parser.ts` — the canonical
  approach to LaTeX-log tokenising: the `(`/`)` file stack, error/warning/box
  regexes, the line-wrap de-wrapping, and the severity buckets. Learn the rules;
  do **not** copy the regexes or structure verbatim — re-derive your own.
- `services/web/frontend/js/ide/human-readable-logs/HumanReadableLogs.ts` — how
  raw messages can be mapped to friendlier text (out of scope here, but shows the
  problem taxonomy). Study only.
- `services/web/frontend/js/features/pdf-preview/util/output-files.ts` — how the
  frontend locates the `output.log` artefact among compile outputs. Learn the
  artefact-resolution pattern (we already have spec-23 storage; mirror the idea).

> Note: Overleaf parses logs **client-side** in TypeScript; Inkstave parses
> **server-side** in Python and ships structured JSON. The parsing *rules* are
> the same public LaTeX-log conventions, but the implementation is independent.

## 7. Acceptance criteria

Using checked-in fixture logs (real Tectonic `output.log` captures committed as
test data — no compile at test time):

1. **Error with `l.<n>`.** A log containing an `! Undefined control sequence`
   followed by `l.42 …` yields one `error` `Problem` with `line == 42` and the
   correct `file` from the open-paren stack.
2. **file:line: form.** A log line `./main.tex:7: Some error` yields an `error`
   with `file == "main.tex"` (normalised), `line == 7`.
3. **LaTeX warning with input line.** `LaTeX Warning: Reference `fig:x'
   undefined on input line 10.` yields a `warning`, `rule == "undefined-ref"`,
   `line == 10`.
4. **Package warning, multi-line.** A wrapped `Package hyperref Warning:` message
   spanning two physical lines is de-wrapped into one `message` with the package
   captured in `rule == "package-warning"`.
5. **Overfull hbox range.** `Overfull \hbox … at lines 12--14` yields an `info`
   with `rule == "overfull-hbox"`, `line == 12`, `end_line == 14`.
6. **File attribution across includes.** A problem emitted while
   `(sections/intro.tex …` is open on the stack resolves `file ==
   "sections/intro.tex"`.
7. **Counts.** `CompileProblems.errors/warnings/infos` equal the number of
   problems of each severity.
8. **Resilience.** A truncated/garbage log parses without raising and yields a
   (possibly empty) list; the `LOGPARSE_MAX_LOG_BYTES` truncation path emits the
   synthetic truncation `info`.
9. **Endpoint.** `GET …/compiles/{id}/problems` returns `200` with the parsed
   payload for a seeded log; `404 log_unavailable` when no log; `401/403` for
   unauthenticated/non-member.
10. **Problems panel jump.** Clicking a panel row with `file`/`line` opens that
    document and scrolls to the line (component test with mocked API).
11. **Inline diagnostics.** With problems loaded for the open file, the editor
    shows CM diagnostics at the matching lines with the correct severities;
    problems for *other* files do not appear in the current editor.
12. **Refresh on recompile.** A second compile result replaces the previous
    diagnostics and panel contents.
13. **Budget.** Spec-27 tests run in well under the 2-minute global budget
    (target < 5s for backend unit + integration).

## 8. Test plan

> No real LaTeX compile in the fast tier — use committed fixture logs.

- **Unit (pytest):** `parse_latex_log` against a battery of fixture logs and
  hand-crafted snippets covering every rule in §5.2.1 (errors with/without
  `l.n`, `file:line:` form, each warning class, overfull/underfull ranges,
  undefined ref/cite, nested file stack, line-wrap de-wrapping, garbage input,
  truncation cap, `LOGPARSE_MAX_PROBLEMS` cap). Assert exact `severity/file/
  line/end_line/rule`.
- **Integration (pytest + httpx, test DB, fake Redis):** the problems endpoint
  with the output store seeded with a fixture `output.log` (reuse spec-23's test
  seam): success, `log_unavailable` 404, `401`/`403`, and the compile-result
  summary counts if folded in.
- **Unit (Vitest):** `problems.ts` client decoding; the CM `Problem→Diagnostic`
  mapping helper (severity map, range computation, file filtering).
- **Component/E2E (Vitest+RTL or Playwright with mocked API):** problems panel
  grouping + row click → open doc + scroll (criterion 10); inline diagnostics
  appear for the open file and refresh on a second mocked compile (criteria
  11–12).
- **Performance/budget note:** parsing is pure CPU on tiny fixtures (KB), thread-
  offloaded for large logs; no network, no compile, no LLM. Fixtures are small
  and reused across cases.

## 9. Definition of Done

- [ ] All requirements in §5 implemented (parser, service, endpoint, problems
      panel, inline CM diagnostics).
- [ ] All acceptance criteria in §7 pass.
- [ ] All tests in §8 written and green.
- [ ] Full suite runs in < 2 minutes.
- [ ] Lint/format/type-check clean (ruff + mypy/pyright; ESLint + Prettier).
- [ ] `LOGPARSE_MAX_LOG_BYTES`, `LOGPARSE_WRAP_WIDTH`, `LOGPARSE_MAX_PROBLEMS`
      documented in `.env.example`; a short ADR in `docs/` records the parser
      rules and severity mapping.
- [ ] No Overleaf code copied (the parser is an independent implementation).
