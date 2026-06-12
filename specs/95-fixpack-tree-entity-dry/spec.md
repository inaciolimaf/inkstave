# Spec 95 — Fix-Pack: TreeEntity-fetch DRY-up & dead re-export (requirements)

## 1. Summary

This fix-pack removes a copy-pasted database lookup that appears in **four**
places and deletes a **dead re-export** line. The
`select(TreeEntity).where(id == entity_id, project_id == project_id)` query plus
its null-check is duplicated in `tree_service._get_entity`,
`document_service._get_doc_entity`, `file_service._get_file_entity`, and inline
in the collab WebSocket join check (`collab/ws/connection.py`). The doc/file
variants additionally assert the fetched entity is a doc/file. This pack
extracts **one** shared async helper and routes all four sites through it,
preserving every existing exception type and message. It also removes a
`_ = (...)` "backwards-compatible access" line in `services/sharing.py` that has
**zero** importers anywhere in the repo. No observable behaviour changes.

**Severity breakdown:**
- minor: 1 (`#TE-1` duplicated TreeEntity fetch in four places)
- nit: 1 (`#TE-2` dead `_ = (...)` re-export in `sharing.py`)

> There is **no Overleaf equivalent** for either issue: both are internal
> Inkstave hygiene. Section 6 records this explicitly.

## 2. Files in scope

Edit **only** these files.

```
backend/src/inkstave/services/tree_service.py
backend/src/inkstave/services/document_service.py
backend/src/inkstave/services/file_service.py
backend/src/inkstave/collab/ws/connection.py
backend/src/inkstave/services/sharing.py
backend/tests/unit/                (new/updated unit test files may be added here)
```

**Helper placement:** if the shared helper needs a home, put it in
`tree_service.py` (preferred — it already owns the tree query and the
`EntityNotFoundError` import) **or** a small new module
`backend/src/inkstave/services/tree_common.py`. The implementer chooses; **if a
new `tree_common.py` module is added it is implicitly in scope.** Do not place
the helper anywhere else.

If a fix appears to require another file, stop and report.

## 3. Goals

- Exactly **one** TreeEntity-fetch helper exists, used by all four former sites.
- The helper raises the **existing** `EntityNotFoundError` (from
  `services/tree_errors.py`, re-exported via `tree_service`) when the row is
  missing, and the **existing** wrong-type errors when an `expected_type` is
  requested and does not match.
- Every call site raises the **same** exception types and messages as before.
- The dead `_ = (_active_project, _now, _invite_by_token)` line in `sharing.py`
  is gone.
- All existing tree / document / file / collab tests stay green; the suite stays
  under 2 minutes.

## 4. Non-goals (explicitly out of scope)

- Do not change endpoint signatures, response models, or HTTP status codes.
- Do not rename or remove the public service functions (`get_file`,
  `ensure_document`, etc.).
- Do not delete the `_active_project` / `_now` / `_invite_by_token` helper
  *functions* themselves unless they are now wholly unused **and** removing them
  is trivially in scope; prefer removing only the dead `_ = (...)` assignment to
  stay minimal (see `#TE-2`).
- Do not "improve" unrelated queries in the touched files.

## 5. Detailed requirements / Issues to fix

### 5.1 — `#TE-1` Duplicated TreeEntity-fetch + null-check in four places (minor)

- **Files:**
  - `backend/src/inkstave/services/tree_service.py` (`_get_entity`, ~line 91)
  - `backend/src/inkstave/services/document_service.py` (`_get_doc_entity`, ~line 50)
  - `backend/src/inkstave/services/file_service.py` (`_get_file_entity`, ~line 83)
  - `backend/src/inkstave/collab/ws/connection.py` (inline, ~line 52–62)
  - (helper home) `tree_service.py` **or** new `services/tree_common.py`
- **Problem:** The same lookup is written four times:

  ```python
  entity = (
      await session.execute(
          select(TreeEntity).where(
              TreeEntity.id == entity_id, TreeEntity.project_id == project_id
          )
      )
  ).scalar_one_or_none()
  if entity is None:
      raise EntityNotFoundError()
  ```

  - `tree_service._get_entity` raises `EntityNotFoundError()`.
  - `document_service._get_doc_entity` additionally raises `NotADocumentError()`
    when `entity.type is not TreeEntityType.doc`
    (`document_service.py:25` / `:60`).
  - `file_service._get_file_entity` additionally raises `NotAFileError()` when
    `entity.type is not TreeEntityType.file`
    (`file_service.py:30` / `:93`); note it raises
    `tree_service.EntityNotFoundError()` for the missing case.
  - `collab/ws/connection.py` runs the same query **with an extra**
    `TreeEntity.type == TreeEntityType.doc` in the `where(...)` clause and, on
    `None`, returns the `CLOSE_NOT_FOUND` close code (it does **not** raise — it
    is a WebSocket join check that maps misses to a 4404-class close code).
- **Fix:** Extract a single shared async helper, e.g.:

  ```python
  async def get_entity(
      session: AsyncSession,
      project_id: UUID,
      entity_id: UUID,
      *,
      expected_type: TreeEntityType | None = None,
  ) -> TreeEntity:
      """Fetch a TreeEntity scoped to a project, optionally asserting its type.

      Raises EntityNotFoundError when the row is missing; when ``expected_type``
      is given and does not match, raises the type-specific error
      (NotADocumentError for ``doc``, NotAFileError for ``file``).
      """
  ```

  Requirements for the helper and the refactor:
  1. **Inspect first.** Before writing, read `services/tree_errors.py`
     (`EntityNotFoundError`), `document_service.py` (`NotADocumentError`), and
     `file_service.py` (`NotAFileError`) to copy the exact exception types and
     messages. Do not invent new error classes or messages.
  2. **Missing row** → raise `EntityNotFoundError()` (the same class all three
     services already use; `file_service` references it as
     `tree_service.EntityNotFoundError`).
  3. **`expected_type=TreeEntityType.doc`** → after the null-check, raise
     `NotADocumentError()` if `entity.type is not TreeEntityType.doc`.
  4. **`expected_type=TreeEntityType.file`** → raise `NotAFileError()` if
     `entity.type is not TreeEntityType.file`.
  5. **No `expected_type`** → return the entity with no type assertion (current
     `_get_entity` behaviour).
  6. **Where the type-specific errors live:** `NotADocumentError` and
     `NotAFileError` are defined in `document_service.py` / `file_service.py`,
     which would create an import cycle if the helper lives in `tree_service.py`
     and tries to import them. Avoid the cycle with the **least invasive**
     approach — preferred options, in order:
     - Keep each service's wrong-type assertion **in the calling service**
       (i.e. the helper handles only the query + `EntityNotFoundError`; each
       service calls `get_entity(...)` then performs its own
       `if entity.type is not ...: raise NotADocumentError()` check). This still
       removes the duplicated query + null-check (the actual duplication) and
       keeps zero new imports. **This is the recommended approach.**
     - *Or* pass the wrong-type exception **factory** into the helper
       (e.g. `wrong_type_error: Callable[[], Exception] | None`) so the helper
       stays type-agnostic and no cross-module import is introduced.
     Do **not** move `NotADocumentError` / `NotAFileError` out of their modules.
  7. **Refactor all four sites** to call the helper:
     - `tree_service._get_entity` → delegate to `get_entity(...)` (or become the
       helper itself if the helper lives here; keep the `_get_entity` name as a
       thin alias if other code in `tree_service` calls it, to avoid touching
       unrelated lines).
     - `document_service._get_doc_entity` → call the helper, then assert
       doc-type (or pass `expected_type=TreeEntityType.doc` per option 6b).
     - `file_service._get_file_entity` → call the helper, then assert file-type.
     - `collab/ws/connection.py` → call the helper with
       `expected_type=TreeEntityType.doc`, wrap the `EntityNotFoundError` (and
       `NotADocumentError`) raised by the helper and **map them to the existing
       `CLOSE_NOT_FOUND` return** so the WebSocket join still returns
       `(CLOSE_NOT_FOUND, False)` exactly as today. The collab path must **not**
       start raising where it previously returned a close code. (Catch the
       helper's exceptions locally and translate to the close-code return.)
  8. **Behaviour parity:** after the refactor, missing-entity and wrong-type
     cases must raise the **same** exception types/messages (services) or return
     the **same** close code (collab) as before. Do not change the public return
     types of `_get_doc_entity` / `_get_file_entity` / the collab check.

### 5.2 — `#TE-2` Dead `_ = (...)` re-export in `sharing.py` (nit)

- **File:** `backend/src/inkstave/services/sharing.py` (~line 92–93)
- **Problem:** The line

  ```python
  # Re-exported private helpers retained for backwards-compatible access via the
  # ``sharing`` module path (used by tests and internal callers).
  _ = (_active_project, _now, _invite_by_token)
  ```

  claims the helpers are retained "for backwards-compatible access … used by
  tests and internal callers", but a repo-wide grep for
  `sharing._active_project` / `sharing._now` / `sharing._invite_by_token`
  returns **zero** external usages. The `_ = (...)` line is a no-op that only
  silences "imported but unused" lint warnings for names nothing else consumes.
- **Fix:**
  1. **Verify** there are no importers/users of those names anywhere in the repo
     (e.g. `grep -rn "sharing\._active_project\|sharing\._now\|sharing\._invite_by_token" backend/`
     and a search for direct `from ... import _active_project, _now, _invite_by_token`).
     Confirm the count is zero before deleting.
  2. **Remove** the dead `_ = (_active_project, _now, _invite_by_token)`
     assignment (and its now-stale leading comment).
  3. If, after removing the assignment, the imports of `_active_project`,
     `_now`, and/or `_invite_by_token` at the top of `sharing.py`
     (~lines 21, 42) become genuinely unused **and** are still referenced
     nowhere else in the module, remove those now-unused imports too so lint
     stays clean. If any of them is still used elsewhere in the module, leave
     that import. Do **not** delete the helper *functions* in their source
     modules — only the dead assignment and any imports it alone kept alive.
     Prefer the minimal change: if cleaning the imports balloons scope, the
     baseline requirement is just removing the `_ = (...)` line and keeping the
     module lint-clean.

### 5.3 Configuration

No new env vars, config files, or feature flags. Nothing to add to
`.env.example`.

## 6. Overleaf reference (study only — never copy)

> **No Overleaf equivalent.** Both issues are internal Inkstave code-hygiene
> items (de-duplicating a SQLAlchemy query and removing a dead Python
> assignment). There is nothing to read in `../overleaf/`; do not look for or
> copy any Overleaf code for this pack.

## 7. Acceptance criteria

Each is independently verifiable.

1. **`#TE-1` single helper:** Exactly **one** TreeEntity-fetch helper exists
   (in `tree_service.py` or `tree_common.py`); the four former sites
   (`tree_service._get_entity`, `document_service._get_doc_entity`,
   `file_service._get_file_entity`, the `collab/ws/connection.py` inline query)
   no longer each contain their own
   `select(TreeEntity).where(...).scalar_one_or_none()` + null-check — they
   delegate to the helper. (Grep: the
   `select(TreeEntity).where(TreeEntity.id == entity_id` pattern appears in only
   one place.)
2. **`#TE-1` missing-entity parity:** Fetching a missing entity through the
   helper raises `EntityNotFoundError` with the unchanged message
   ("Tree entity not found.").
3. **`#TE-1` wrong-type parity:** A non-doc entity requested as a doc still
   raises `NotADocumentError`; a non-file entity requested as a file still
   raises `NotAFileError`; messages unchanged.
4. **`#TE-1` collab parity:** The WebSocket join check still returns
   `(CLOSE_NOT_FOUND, False)` for a missing or non-doc document id (it does
   **not** raise out of the join check).
5. **`#TE-2` dead line gone:** `grep -n "_active_project, _now, _invite_by_token" backend/src/inkstave/services/sharing.py`
   returns nothing; `sharing.py` is lint-clean (no unused-import warnings).
6. **No behaviour change:** all existing tree/document/file/collab/sharing tests
   pass unchanged (no test assertions needed editing to accommodate a new
   message or status).
7. The full test suite is green and runs in **< 2 minutes** (`just test-timed`).

## 8. Test plan

> Keep the combined suite under 2 minutes. No real DB sleeps; reuse existing
> async test patterns and fixtures.

- **Stay green:** All existing tests covering the file tree, documents, files,
  the collab WebSocket join, and sharing must continue to pass **unchanged**.
  Their continued green status is the primary proof that behaviour did not
  change.
- **New focused unit test for the helper** (under `backend/tests/unit/`, e.g.
  `backend/tests/unit/test_tree_get_entity_95.py`), covering in isolation:
  - **found:** the helper returns the matching `TreeEntity` for a present
    `(project_id, entity_id)` pair;
  - **not found:** a missing pair raises `EntityNotFoundError`;
  - **wrong expected_type:** requesting `expected_type=TreeEntityType.doc` on a
    non-doc entity raises `NotADocumentError`, and
    `expected_type=TreeEntityType.file` on a non-file entity raises
    `NotAFileError` (cover at least one of each, plus the matching-type happy
    path returning the entity);
  - use an in-memory / fixture-backed async session consistent with the existing
    service unit tests (no new infrastructure, no real network/Redis).
- **Performance/budget note:** The new test is a thin, in-memory unit test and
  adds negligible time. Run `just test-timed` (xdist) to confirm the suite stays
  under the 2-minute budget. The budget is **unaffected** by this pack.

## 9. Definition of Done

- [ ] `#TE-1` and `#TE-2` both fixed exactly as described in §5.
- [ ] Exactly one TreeEntity-fetch helper remains, used by all four former sites.
- [ ] Missing-entity and wrong-type cases raise the **same** exception
      types/messages as before; the collab join still returns the same close
      code.
- [ ] The dead `_ = (...)` line in `sharing.py` is removed and the module is
      lint-clean.
- [ ] All acceptance criteria in §7 pass.
- [ ] The new helper unit test in §8 is written and green; all pre-existing
      tests pass unchanged.
- [ ] Full suite runs in **< 2 minutes** (`just test-timed`).
- [ ] Lint/format/type-check clean (`ruff`, type checker as configured).
- [ ] Edits limited to the files in §2 (plus an optional new `tree_common.py`
      and the new unit test) — no out-of-scope files touched.
- [ ] No Overleaf code copied (none exists for this pack); stack unchanged.
