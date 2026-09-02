# ADR 0106 — Complexity + security lint thresholds

**Status:** accepted · **Phase:** 7 — Hardening, packaging & docs

## Context

The backend passed `ruff` (`E`, `F`, `I`, `UP`, `B`, `ASYNC`) and strict `mypy`,
but nothing bounded the *shape* of a function. Several orchestration functions had
drifted well past what a reader can hold in their head — the SyncTeX parser's
`_parse` was 101 lines with a cyclomatic complexity of 25, the compile job body 59
statements — and bandit's security rules had never been switched on at all.

This ADR records the thresholds now enforced, and why each one is set where it is.

## The budget

| Rule | Threshold | Ruff default | Why |
| --- | --- | --- | --- |
| `C901` cyclomatic complexity | **6** | 10 | Past six independent paths, a function stops fitting in one reading. The tightest of the set, and the one that did most of the work. |
| `PLR0915` statements | **50** | 50 | Ruff's default; restated so the whole budget is readable in one place. |
| `PLR0912` branches | **12** | 12 | As above. |
| `PLR0911` returns | **6** | 6 | As above. |
| `PLR0913` arguments | **8** | 5 | *Loosened.* DI-heavy FastAPI routes and service constructors legitimately take more than five; eight still forces a parameter object when an argument list becomes a bag of identity fields. |
| `RUF100` unused `noqa` | **zero** | — | A suppression that silences nothing is a lie about the code. |
| `S` (bandit) | **on** | — | The security surface: `assert` in shipped code, hardcoded credentials, predictable temp paths, silently swallowed exceptions. |
| function length | **30 lines** | — | No ruff equivalent; see below. |

## Function length has no ruff rule

`PLR0915` counts *statements*, not lines, so a function can be 80 lines of wrapped
calls and still pass. `scripts/lint_function_length.py` is a dependency-free AST
check that fills the gap. It counts the code-bearing physical lines of a function
body and **excludes** the signature, blank lines, comment-only lines and the
docstring — documenting a function must never push it over the limit. It runs in
`just lint`, in CI, and as a pre-commit hook.

## What the enforcement changed

Roughly 100 functions were restructured to fit the budget. The recurring shapes:

- **Job/route orchestration → a step pipeline.** `compile/jobs.py`,
  `services/import_jobs.py` and `agent/api/jobs.py` each grew a small state object
  (`_Job`, `_Import`, `RunScope`) that owns "update the row, commit, publish the
  event", so each step reads as one call.
- **Long parsers → a scanner object.** `agent/context/parser.py` and
  `synctex/parser.py` moved their mutable pass state into a dataclass with one
  small handler per token kind, and a dispatcher that routes to them.
- **Long argument lists → parameter objects.** `AuditSubject`/`AuditUsage`,
  `repo.NewDiff`, `OutputRow` and `RunScope` replaced clusters of positional
  identity fields. This also makes the fields impossible to mis-order at a call site.
- **Duplicated SSE loops → one pump.** The compile, project-import and agent-run
  streams all polled Redis and interleaved keep-alives by hand; `inkstave/sse.py`
  now owns the poll loop and the keep-alive clock.

## The security rules, case by case

- **`S101` (`assert`) in `src`.** Ten sites, all internal invariants. `assert` is
  stripped under `python -O`, so the ones guarding real data (a history row with
  neither an inline payload nor a blob key) became explicit raises via the new
  `inkstave.invariants.require`; the rest were restructured away.
- **`S110`/`S112` (silently swallowed exceptions).** Three sites now log at DEBUG
  before continuing. Each was genuinely best-effort — a container kill, an abrupt
  WebSocket disconnect, a route matcher that raises — so the behaviour is unchanged
  and the failure is now visible.
- **`S105`/`S108` false positives.** Rate-limit *policies* (`"5/3600"`), the OAuth
  scheme name `"bearer"`, the container-internal `/tmp` tmpfs mount and the two
  scratch-directory settings defaults carry a narrow `# noqa` with the reason.
- **Tests are exempt from the credential/sandbox heuristics only.** `assert` *is*
  the assertion mechanism, fixture passwords are deliberately fake, and `0.0.0.0`
  appears in bind-address assertions. Tests are held to the same *complexity* and
  *length* budget as `src`.

## Deliberately not done

- **`BLE001` (blind `except`) was not enabled.** Five sites carried a documented
  `# noqa: BLE001`; since the rule is not part of the contract those directives were
  inert, so each became a plain `# broad on purpose: <reason>` comment. Turning the
  rule on would mean auditing 21 further sites — real work, but a different change
  from the one this ADR covers.
- **Migrations stay unlinted** (`extend-exclude`), as they already were: they are
  generated, and a released migration is never edited.
