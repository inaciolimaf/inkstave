# Spec 99 — Fix-Pack: Query Efficiency & Bounded Tree Fetches (requirements)

## 1. Summary

This fix-pack closes **three confirmed performance/safety issues** in the
file-read and tree/compile read paths that were validated against the codebase:

1. an **N+1 query** in `api/routes/files.py` — every file get/upload/download
   issues a *separate* `SELECT` on `TreeEntity` just to fetch the entity's name;
2. an **unbounded full-tree fetch** in `tree_service.get_tree`, reached from the
   tree routes, which loads *all* `TreeEntity` rows for a project with no cap; and
3. **unbounded full-project fetches** in `compile/sources.py`, which load the
   whole tree plus all docs/files per compile with no bound.

The fixes are the **smallest changes** that (a) eliminate the per-row name
lookup and (b) impose a single, configurable, generously-defaulted upper bound on
how many tree nodes a read may materialise, failing with a clear, existing-style
domain error when exceeded. **Behaviour for normal-size projects is unchanged**;
existing files/tree/compile tests stay green.

> **No Overleaf equivalent.** These are Inkstave-internal query-shape and
> safety-cap fixes against Inkstave's own SQLAlchemy models, services, and
> settings. There is nothing to study or copy in `../overleaf/`.

## 2. Context & dependencies

- **Depends on:** specs 12 (file tree + `tree_service`), 13 (documents),
  14 (binary files + `files.py`), 21–23 (compile + `compile/sources.py`), 52/57
  (settings/config-guard conventions), and **spec 95** (refactors
  `tree_service.py`).
- **ORDER constraint:** this pack edits `services/tree_service.py`, which
  **spec 95 also refactors**. **Spec 99 must be applied AFTER spec 95**, so its
  change lands on the refactored module. If spec 95 is not yet applied, stop and
  report.
- **Unlocks:** nothing structural; this is hardening. Later specs benefit from the
  bounded read path but do not require it.
- **Affected areas:** backend only (routes, services, compile sources, config) +
  backend tests.

## 3. Goals

- Reading a single file performs **no extra per-file `TreeEntity` `SELECT`** for
  the entity name.
- `get_tree` and the compile source iterators have an **enforced upper bound** on
  the number of tree nodes they will materialise, with a clear domain error past
  the limit (or a documented, defensible cap).
- The bound is **configurable** via the existing settings pattern and has a
  **generous default** so existing tests and real projects are unaffected.
- All current response/return shapes (`FileRead`, `TreeRead`, compile inputs) are
  unchanged for normal-size projects.

## 4. Non-goals (explicitly out of scope)

- No pagination of the tree API or compile inputs (the tree is returned whole;
  this pack only **caps** it, it does not page it).
- No schema/migration changes; no new indexes.
- No change to authorization, error envelope shape, or route signatures.
- No edits to any file outside §5 / the §2-equivalent scope list below.
- No refactoring of unrelated tree-service operations.

## 5. Files in scope

Edit **only** these files:

```
backend/src/inkstave/api/routes/files.py
backend/src/inkstave/compile/sources.py
backend/src/inkstave/api/routes/tree.py
backend/src/inkstave/services/tree_service.py
backend/src/inkstave/config_groups.py        (the new bound setting lives here; Settings composes it)
backend/src/inkstave/services/tree_errors.py (only if a new domain error is added; see §6.2)
.env.example                                  (document the new bound var, matching existing entries)
backend/tests/integration/                    (new/updated tests may be added here)
backend/tests/unit/                            (new/updated tests may be added here)
```

> If a fix appears to require a file not listed here, **stop and report** rather
> than reaching outside the set. `tree_errors.py` is listed conditionally: touch
> it only if you choose to add a dedicated domain error for the cap (§6.2);
> otherwise leave it untouched.

## 6. Issues to fix

### 6.1 — N+1 `TreeEntity` SELECT per file read

- **File:** `backend/src/inkstave/api/routes/files.py:44-54` (`_entity_name`,
  `_read`); also called at `:129` in `download_file`.
- **Problem:** `_entity_name(session, entity_id)` runs a **separate**
  `SELECT TreeEntity.name WHERE id = …` for **every** file, and `_read()` calls it
  on **every** file get/upload/download. So a single-file response costs two
  round-trips (the file row + the name), and any future bulk listing would be a
  textbook N+1.
- **Fix:** Eliminate the per-row name query. Choose the **lowest-risk** of:
  - **(preferred)** eager-load the related `TreeEntity` when the `File` is fetched
    — add a `selectinload(File.entity)` / `joinedload(File.entity)` (or a single
    `JOIN`) in the `file_service` fetch the route already calls, and read
    `file_row.entity.name` in `_read()`; **or**
  - pass the **already-known** entity name down from the caller (e.g. when the
    caller created/loaded the entity in the same request) so `_read()` needs no
    extra lookup.
  Whichever you pick, `_read()` must no longer issue a standalone `TreeEntity`
  `SELECT`, and `download_file`'s filename derivation (`:129`) must use the same
  eager-loaded/passed name rather than a second `_entity_name` call. **Keep the
  `FileRead` response shape identical** (`name` still populated from the entity).
  Confirm `File` has (or add a benign, read-only) relationship to `TreeEntity`
  only if the model already supports it; **do not add a migration**.

### 6.2 — Unbounded full-tree fetch in `get_tree`

- **File:** `backend/src/inkstave/services/tree_service.py:62-64` (`get_tree`),
  reached from `backend/src/inkstave/api/routes/tree.py:51,71`.
- **Problem:** `get_tree` does `select(TreeEntity).where(project_id == …)` and
  returns **all** rows with **no cap**. A pathological project (tens of thousands
  of nodes) would materialise the entire tree into memory on every tree read and
  on every entity mutation response (`_read` calls `get_tree` to compute paths).
- **Fix:** Add a **sane, configurable upper bound** and enforce it in `get_tree`:
  - Add a setting `tree_max_nodes: int` to `config_groups.py` (alongside the other
    compile/limit ints, e.g. near `compile_max_input_files`), with a **generous
    default** (`50_000`) so normal projects and all existing tests are unaffected.
    Document it in `.env.example` matching the style of neighbouring entries
    (`TREE_MAX_NODES=50000  # safety cap on tree nodes materialised per read`).
  - In `get_tree`, fetch and, when the materialised count **exceeds**
    `tree_max_nodes`, raise a **clear, existing-style domain error**. Prefer adding
    a `TreeTooLargeError(AppError)` to `tree_errors.py` with
    `status_code = 422` (or `409`) and `error_type = "tree_too_large"`, following
    the exact pattern of the sibling errors there, and re-export it via the
    `tree_service` `__all__` list as the other tree errors are. Implement the cap
    with a bounded fetch (e.g. `select(...).limit(tree_max_nodes + 1)`), so you
    detect "over the limit" without loading more than `limit+1` rows.
  - `get_tree` must accept the limit from settings (read via the existing
    `get_settings()` accessor used elsewhere in services, **not** `os.environ`).
    If `get_tree`'s signature must change to receive the cap, keep it
    backward-compatible (default param) so existing callers in `tree.py` and
    `compile/sources.py` keep working unchanged for normal projects.
  - If, after inspecting the code, you judge a hard error is too risky for an
    existing caller, the **documented alternative** is a defensive `.limit(cap)`
    that silently truncates **plus** a code comment justifying why truncation is
    acceptable there. Pick the lowest-risk option and **justify the choice in a
    short comment**; the default expectation is the explicit error.

### 6.3 — Unbounded full-project fetches in compile sources

- **File:** `backend/src/inkstave/compile/sources.py:27-64` — `_entities_by_id`
  (`:27-31`), and `iter_documents` / `iter_files` (`:38-64`).
- **Problem:** Each compile loads the **entire** tree via `_entities_by_id`
  (`select(TreeEntity).where(project_id == …)`, no bound) and then **all** docs
  and **all** files for the project, again unbounded. A pathological project makes
  every compile load the whole tree into a dict and iterate every row.
- **Fix:** Bound the tree materialisation **consistently with #6.2**:
  - Route `_entities_by_id`'s tree load through the same cap — either call the
    bounded `tree_service.get_tree` (which already enforces `tree_max_nodes`) and
    build the `{id: entity}` dict from its result, or apply the identical
    `tree_max_nodes` `.limit(cap+1)` + same error here. Prefer **reusing
    `get_tree`** so the cap lives in one place.
  - For the docs/files iterators (`iter_documents`, `iter_files`): a compile
    legitimately needs every doc/file in the (now-bounded) tree, so they may stay
    full-table iterators **but** must be **defensively capped** by the same
    `tree_max_nodes`-derived bound (the tree cap already limits how many entities
    can match), and you must add a short comment stating that the compile path is
    intentionally whole-project and is protected by the tree cap. Compile already
    enforces `compile_max_input_files` / `compile_max_input_bytes` downstream
    (spec 21); reference that in the comment so it is clear the iterators are not
    the only guard.
  - **Keep compile inputs identical for normal-size projects** — the same paths,
    same contents, same order of yielding.

## 7. Acceptance criteria

Each is independently verifiable.

1. **#6.1** Reading a single file (`GET /projects/{id}/files/{eid}`) issues **no
   standalone `TreeEntity` SELECT** for the name — verifiable by counting emitted
   queries (e.g. a SQLAlchemy event/echo capture asserting exactly one fetch round
   for the file, with the entity eager-loaded) **or** by asserting the route reads
   `file_row.entity.name` from an eager-loaded relationship rather than calling
   `_entity_name`.
2. **#6.1** `FileRead` for get / upload / download is **byte-for-byte identical**
   to before (same `name`, all other fields unchanged); `download_file`'s
   `Content-Disposition` filename is unchanged.
3. **#6.2** A `tree_max_nodes` setting exists in `config_groups.py` with a generous
   default (`50_000`) and is documented in `.env.example`.
4. **#6.2** `get_tree` enforces the cap: for a project whose node count exceeds
   `tree_max_nodes`, it raises the clear domain error (`TreeTooLargeError` /
   `tree_too_large`) — or, if the documented-truncation alternative was chosen, it
   never materialises more than the cap and a justifying comment is present.
5. **#6.2** For a normal-size project (≤ cap), `get_tree` returns **exactly the
   same rows** as before and the tree routes return an unchanged `TreeRead`.
6. **#6.3** The compile source tree load is bounded by the same cap (reuses
   `get_tree` or applies the identical limit/error); for a normal-size project the
   compile inputs (paths, contents, order) are **identical** to before.
7. Existing files / tree / compile tests remain **green**; no response shape,
   status code, or error envelope changed for in-range projects.
8. The full test suite is green and runs in **< 2 minutes** (`just test-timed`).

## 8. Test plan

> Keep the combined suite under 2 minutes. No real LaTeX/SMTP/Redis; mock/stub.
> All new tests are in-memory / DB-fixture-backed and fast; no real sleeps.

- **Stay green:** all existing `files`, `tree`, and `compile` tests must continue
  to pass after the edits (shapes and statuses unchanged).
- **New / updated tests proving each fix:**
  - **#6.1 (query count / eager-load):** add an integration or unit test asserting
    that a single file read does **not** perform the extra name lookup — either
    count SQL statements via a SQLAlchemy `before_cursor_execute` listener (assert
    the `tree_entities` name `SELECT` is **absent**) or assert the route obtains
    the name from the eager-loaded `File.entity` relationship. Keep it to one or
    two files so it stays fast.
  - **#6.2 (cap triggers):** add a test that, with `tree_max_nodes` monkeypatched
    to a tiny value (e.g. `2`), creating more entities than the cap makes
    `get_tree` (and the `GET …/tree` route) raise the expected
    `TreeTooLargeError` / return the mapped status — and that **at the cap** the
    call still succeeds. Use the tiny-cap override so the test needs only a handful
    of rows (do **not** insert 50 000 rows).
  - **#6.3 (compile bound):** with the same tiny `tree_max_nodes` override, assert
    the compile source iterators respect the cap (raise/truncate as #6.2 does);
    and, with the default cap, assert a normal small project yields the **same**
    document/file paths and contents as before (a snapshot/equality check against
    the pre-change behaviour).
- **Performance/budget note:** every new test uses a monkeypatched tiny cap and a
  handful of fixture rows, so it adds negligible time. Run `just test-timed`
  (xdist) to confirm the 2-minute budget is unaffected.

## 9. Definition of Done

- [ ] All three issues in §6 fixed with the smallest viable change.
- [ ] All acceptance criteria in §7 pass.
- [ ] New/updated tests in §8 written and green.
- [ ] `FileRead`, `TreeRead`, and compile inputs unchanged for normal-size projects.
- [ ] `tree_max_nodes` added in `config_groups.py` with a generous default and
      documented in `.env.example`; any new domain error follows the
      `tree_errors.py` pattern and is re-exported via `tree_service.__all__`.
- [ ] Spec 95 was applied first (ORDER constraint honoured); only §5 files touched.
- [ ] Full suite runs in **< 2 minutes** (`just test-timed`).
- [ ] Lint/format/type-check clean (`ruff`, type checker as configured).
- [ ] No Overleaf code copied; stack unchanged.
