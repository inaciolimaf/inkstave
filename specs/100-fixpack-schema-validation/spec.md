# Spec 100 — Fix-Pack: Request-Schema Validation (requirements)

## 1. Summary

This fix-pack tightens **two request schemas** so malformed input is rejected at
the Pydantic boundary as a clean **422** rather than surviving until the service
layer, where it surfaces as a later domain error (or, for the status filter, as
a silently-empty result). Two issues are addressed: (a) the tree-entity `name`
fields (`CreateEntityIn`, `RenameEntityIn`) carry no length constraint, so the
255-character limit is only enforced at runtime in `tree_service` via
`validate_name_segment`; (b) the agent diff-list endpoint accepts an arbitrary
`?status=` string and validates it manually inside the handler. Both are
hardening fixes with **no behaviour change for valid inputs**.

## 2. Context & dependencies

- **Depends on:** specs 12 (file-tree schemas/service), 49–46 (agent diffs API).
  They must already be implemented and their tests passing.
- **Unlocks:** nothing functionally new — this is a fail-fast hardening pass.
- **Affected areas:** backend (request schemas + one route), backend tests.

## 3. Files in scope

Edit **only** these files. Make the smallest change that resolves each issue.

```
backend/src/inkstave/schemas/tree.py
backend/src/inkstave/agent/api/routes.py
backend/tests/integration/        (new/updated integration tests may be added here)
backend/tests/unit/               (new/updated unit tests may be added here)
```

Read-only reference (do **not** edit — used only to match constraints exactly):

```
backend/src/inkstave/services/safe_path.py     # MAX_TREE_ENTITY_NAME_LENGTH, validate_name_segment
backend/src/inkstave/services/tree_service.py  # where validate_name_segment is called
backend/src/inkstave/agent/diffs/models.py     # ProposedDiffStatus enum (the real status values)
```

## 4. Goals

- A create/rename request whose `name` is empty or longer than the entity-name
  limit returns **422 at the schema boundary**, before any service call.
- A diff-list request with an invalid `?status=` value returns **422 at the
  schema boundary**, before any manual check in the handler.
- All valid inputs behave exactly as before (same success path, same results).

## 5. Non-goals (explicitly out of scope)

- Removing or weakening `validate_name_segment` (it still enforces illegal
  characters, path separators, reserved device names, control chars, etc.).
- Adding length/format constraints to any other schema or field.
- Changing the diff-list response shape, ordering, or the `include=hunks`
  behaviour.
- Any frontend change.

## 6. Issues to fix

### 6.1 — Tree-entity `name` has no length constraint (fail-fast 422)

- **File:** `backend/src/inkstave/schemas/tree.py` (`CreateEntityIn.name` and
  `RenameEntityIn.name`, around lines 16–28).
- **Problem:** Both `name` fields are plain `str` with no length constraint. The
  real length rule — `MAX_TREE_ENTITY_NAME_LENGTH = 255` in
  `services/safe_path.py` — is enforced only at runtime by `validate_name_segment`
  (called from `tree_service.py` at the create/rename paths, ~lines 145 and 199).
  So an empty or over-long name is rejected **late**, as an
  `InvalidNameError`/domain error from inside the service, rather than as a clean
  **422** at the schema boundary. Spec 52's strict-input posture wants request
  bodies validated up front.
- **Fix:** Add a length constraint to **both** `name` fields:
  `name: str = Field(min_length=1, max_length=255)`. Prefer importing and using
  the existing `MAX_TREE_ENTITY_NAME_LENGTH` constant from
  `inkstave.services.safe_path` (i.e. `max_length=MAX_TREE_ENTITY_NAME_LENGTH`)
  so the schema and service limits cannot drift; if importing it here would
  create an import cycle or is otherwise impractical, hard-code `255` with a
  comment pointing at `MAX_TREE_ENTITY_NAME_LENGTH` and a note that the two must
  stay in sync. Import `Field` from `pydantic` (the module already imports from
  `pydantic`).
  - **Do NOT** remove or alter the service-layer `validate_name_segment` call —
    it also rejects path separators, reserved names, control characters and
    trailing dot/space, which the schema constraint does **not** cover. The
    schema constraint is an *additional* fail-fast guard.
  - **Verify the constraint matches the service limit exactly** (`max_length`
    equals `MAX_TREE_ENTITY_NAME_LENGTH` = 255; `min_length=1` mirrors the
    service's "must not be empty" check).
  - **Whitespace edge note (preserve behaviour):** `validate_name_segment` calls
    `name.strip()` *before* its length check, whereas Pydantic `max_length`
    measures the raw string. A name that is ≤255 chars after stripping but >255
    chars with surrounding whitespace would now 422 at the schema (previously it
    reached the service and was accepted after stripping). This is an acceptable,
    stricter-but-consistent outcome for a hardening pass — surrounding whitespace
    in names is already trimmed away on store. Do not add whitespace-stripping to
    the schema to "match"; just keep `min_length=1, max_length=255`. Document this
    in the test that asserts the happy path uses ordinary (non-padded) names.

### 6.2 — Diff-list `?status=` filter accepts arbitrary strings (fail-fast 422)

- **File:** `backend/src/inkstave/agent/api/routes.py` (`list_diffs`, the
  `status_filter` query parameter ~line 278 and the manual filter ~lines 286–287).
- **Problem:** The endpoint declares
  `status_filter: str | None = Query(None, alias="status")` and then filters rows
  manually with `if status_filter is not None: rows = [r for r in rows if r.status == status_filter]`.
  Any string is accepted; an unknown value (e.g. `?status=bogus`) is **not**
  rejected — it silently matches nothing and returns an empty list, masking a
  client error instead of failing fast.
- **Fix:** Constrain the parameter at the boundary with a `Literal[...]` of the
  **real** diff-status values. Inspect `ProposedDiffStatus` in
  `backend/src/inkstave/agent/diffs/models.py` and use its full value set — at
  time of writing that is: `"proposed"`, `"applied"`, `"partially_applied"`,
  `"rejected"`, `"stale"`, `"superseded"`. Declare the parameter as:
  ```python
  status_filter: Literal[
      "proposed", "applied", "partially_applied", "rejected", "stale", "superseded"
  ] | None = Query(None, alias="status")
  ```
  (or build the `Literal` from the enum values if you prefer a single source of
  truth — but it must enumerate exactly the enum's `.value`s, not a hand-picked
  subset). **Keep** `alias="status"` and the `None` default. `Literal` is already
  imported via `typing` in the agent codebase; add the import if absent in this
  module.
  - The existing manual comparison
    `rows = [r for r in rows if r.status == status_filter]` may **remain** (it is
    now guaranteed to receive only a valid value, so it is no longer a validation
    step — only a filter) **or** be simplified, as long as behaviour for valid
    inputs is identical. Do not introduce a separate manual "is this allowed?"
    check; the `Literal` is the validation. Remove any now-dead manual
    allowed-values guard if one exists.
  - **Preserve valid-input behaviour:** for every valid status value the returned
    rows must be exactly what they were before. `None` (no `status` query param)
    still returns all rows.

## 7. Acceptance criteria

Each is independently verifiable.

1. **6.1 (empty name):** `POST` create-entity (and the rename endpoint) with
   `name=""` returns **422** with a Pydantic validation error (not a later
   `invalid_name`/domain error from the service).
2. **6.1 (over-long name):** create/rename with a `name` of length 256 returns
   **422** at the schema boundary.
3. **6.1 (valid name still works):** create/rename with a normal valid name still
   **succeeds**, and the request still passes through `validate_name_segment`
   (e.g. a name containing a path separator like `a/b` is still rejected by the
   service with the existing `invalid_name` error — proving the service guard was
   not removed).
4. **6.1 (limit matches):** the schema `max_length` equals
   `MAX_TREE_ENTITY_NAME_LENGTH` (255) and `min_length` is `1`.
5. **6.2 (invalid status):** `GET .../sessions/{id}/diffs?status=bogus` returns
   **422** (not an empty `200`).
6. **6.2 (valid status):** each valid status filter (`proposed`, `applied`,
   `partially_applied`, `rejected`, `stale`, `superseded`) returns the **same**
   rows it returned before this change; omitting `status` returns all rows.
7. The full test suite is green and runs in **< 2 minutes** (`just test-timed`).

## 8. Test plan

> Keep the combined suite under 2 minutes. No real LaTeX/SMTP/Redis; mock/stub.

- **Stay green:** all existing tree, agent-diff, and hardening tests must keep
  passing after the edits.
- **New / updated tests proving each fix:**
  - **Tree name constraint (integration, `backend/tests/integration/`):**
    - create-entity with `name=""` → **422**; create-entity with a 256-char
      `name` → **422** (both rejected before the service runs).
    - rename-entity with `name=""` → **422**; rename with a 256-char `name`
      → **422**.
    - **happy path:** create/rename with a valid name (a 255-char name and an
      ordinary short name) → **success**.
    - **service guard intact:** create/rename with `name="a/b"` (a path
      separator) still returns the existing `invalid_name` 422 from
      `validate_name_segment`, proving the service-layer call was not removed.
  - **Diff status filter (integration, `backend/tests/integration/`):**
    - `?status=bogus` → **422**.
    - at least one **valid** `?status=` value returns the expected filtered rows;
      omitting `status` returns all rows for the session. (Reuse the existing
      diff-list test fixtures/seed pattern so the assertion is fast.)
  - **Optional unit (`backend/tests/unit/`):** a tiny Pydantic-level test
    constructing `CreateEntityIn`/`RenameEntityIn` directly to assert
    `ValidationError` on empty/over-long names and success on a 255-char name —
    cheaper than the HTTP roundtrip and documents the constraint.
- **Performance/budget note:** all new tests are schema-level or thin HTTP
  assertions with no real I/O; they add negligible time. The 2-minute budget is
  unaffected. Confirm via `just test-timed` (xdist).

## 9. Definition of Done

- [ ] Both issues in §6 fixed: `CreateEntityIn.name` and `RenameEntityIn.name`
      carry `Field(min_length=1, max_length=255)` (matching
      `MAX_TREE_ENTITY_NAME_LENGTH`); the diff-list `status` filter is a
      `Literal` of the real `ProposedDiffStatus` values.
- [ ] The service-layer `validate_name_segment` call is **unchanged**.
- [ ] All acceptance criteria in §7 pass.
- [ ] New/updated tests in §8 written and green.
- [ ] Valid-input behaviour is unchanged (names and status filters).
- [ ] Full suite runs in **< 2 minutes** (`just test-timed`).
- [ ] Lint/format/type-check clean (`ruff`, type checker as configured).
- [ ] Edits limited to the files in §3 — no out-of-scope files touched.
- [ ] No Overleaf code copied; stack unchanged.
