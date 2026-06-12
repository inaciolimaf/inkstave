# Spec 98 — Fix-Pack: Pydantic mutable-default consistency (requirements)

## 1. Summary

This fix-pack converts **4 bare mutable defaults** (three `list` fields, one
nested `dict` field) on Inkstave's Pydantic v2 settings models to explicit
`Field(default_factory=...)`. This is an **idiomatic-consistency / explicitness**
hardening, **not** a bug fix.

**Important — there is no state-leakage bug today.** Pydantic v2 already
**deep-copies** mutable field defaults for every model instance, so the bare
literals (e.g. `jwt_secret_previous: ... = []`) do **not** leak shared state
between `Settings` instances the way a bare mutable default would in a plain
`dataclass` or a function default argument. The implementer must **not** claim or
imply that this pack fixes a live aliasing bug. The motivation is purely
consistency and readability: other modules in the repo already express mutable
defaults the idiomatic way (e.g. `agent/context/models.py` uses
`Field(default_factory=list)`), and these four fields are the remaining
inconsistent spots. The change must be **behaviour-preserving**.

This pack has **no Overleaf equivalent** (see §6).

## 2. Files in scope

Edit **only** these files.

```
backend/src/inkstave/config_groups.py
backend/src/inkstave/agent/settings.py
backend/tests/unit/                       (new/updated unit test files may be added here)
```

If a fix appears to require any other file, stop and report.

## 3. Goals

- Each of the four listed mutable-default fields uses
  `Field(default_factory=...)`.
- The default **values** produced are byte-for-byte identical to today's.
- `Annotated[..., NoDecode]` typing and any custom decoders/validators on these
  fields remain intact, so env-var parsing is unchanged.
- A unit test documents the intended defaults and proves two independent settings
  instances receive **independent** (non-aliased) mutable objects.

## 4. Non-goals (explicitly out of scope)

- Changing any default value, item ordering, or list/dict contents.
- "Fixing" a state-leakage bug — there is none (see §1).
- Touching env-var decoding, `NoDecode`, or validation-alias behaviour.
- Converting other (immutable) defaults or unrelated fields to factories.
- Editing any file outside §2.

## 5. Detailed requirements

### 5.1 Issues to fix

> Before editing each field, **read the current literal in the real file** and
> reproduce it exactly. The values quoted below are copied from the current
> source but the implementer must re-confirm them against the file at edit time.

#### Issue 1 — `jwt_secret_previous` bare empty-list default

- **File:** `backend/src/inkstave/config_groups.py` (`jwt_secret_previous`,
  around line 90).
- **Problem:** Declared as
  `jwt_secret_previous: Annotated[list[str], NoDecode] = []` — a bare mutable
  list literal as the default. This is inconsistent with the repo's idiomatic
  `Field(default_factory=list)` style (e.g. `agent/context/models.py`).
- **Fix:** Change the default to `Field(default_factory=list)`, keeping the
  `Annotated[list[str], NoDecode]` annotation and any associated validators /
  field decoders **exactly** as they are:
  ```python
  jwt_secret_previous: Annotated[list[str], NoDecode] = Field(default_factory=list)
  ```
  Ensure `Field` is imported (it is already used elsewhere in the module, e.g.
  `rate_limit_login`). Do not change the env-var name or its `NoDecode` decoder.

#### Issue 2 — `upload_allowed_extensions` bare list default

- **File:** `backend/src/inkstave/config_groups.py`
  (`upload_allowed_extensions`, around line 129).
- **Problem:** Declared with a bare mutable list literal default.
- **Fix:** Wrap the **exact same list** in a `default_factory`. The current
  contents are (re-confirm against the file):
  ```python
  [".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".bib",
   ".tex", ".cls", ".sty", ".svg", ".eps", ".csv", ".txt"]
  ```
  Resulting declaration:
  ```python
  upload_allowed_extensions: Annotated[list[str], NoDecode] = Field(
      default_factory=lambda: [
          ".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".bib",
          ".tex", ".cls", ".sty", ".svg", ".eps", ".csv", ".txt",
      ]
  )
  ```
  Alternatively, lift the list into a module-level constant (e.g.
  `_DEFAULT_UPLOAD_ALLOWED_EXTENSIONS`) and reference it from the factory
  (`default_factory=lambda: list(_DEFAULT_UPLOAD_ALLOWED_EXTENSIONS)`). Either
  way the produced default must be **identical** (same items, same order). Keep
  the `Annotated[list[str], NoDecode]` annotation and the field's decoder
  unchanged.

#### Issue 3 — `allowed_upload_mime` bare list default

- **File:** `backend/src/inkstave/config_groups.py` (`allowed_upload_mime`,
  around line 158).
- **Problem:** Declared with a bare mutable list literal default.
- **Fix:** Same approach as Issue 2, preserving the exact contents (re-confirm
  against the file):
  ```python
  ["image/png", "image/jpeg", "image/gif", "image/webp", "image/svg+xml",
   "application/pdf", "text/plain", "application/x-bibtex", "text/x-bibtex"]
  ```
  Resulting declaration:
  ```python
  allowed_upload_mime: Annotated[list[str], NoDecode] = Field(
      default_factory=lambda: [
          "image/png", "image/jpeg", "image/gif", "image/webp",
          "image/svg+xml", "application/pdf", "text/plain",
          "application/x-bibtex", "text/x-bibtex",
      ]
  )
  ```
  Module-constant approach is equally acceptable. Keep `Annotated[..., NoDecode]`
  and the decoder intact.

#### Issue 4 — `agent_model_cost_table` bare nested-dict default

- **File:** `backend/src/inkstave/agent/settings.py` (`agent_model_cost_table`,
  around line 63).
- **Problem:** Declared as a bare mutable nested-`dict` literal default:
  ```python
  agent_model_cost_table: dict[str, dict[str, float]] = {
      "openai/gpt-4o-mini": {"input": 0.00015, "output": 0.0006}
  }
  ```
- **Fix:** Wrap the **exact same nested dict** in a `default_factory`:
  ```python
  agent_model_cost_table: dict[str, dict[str, float]] = Field(
      default_factory=lambda: {
          "openai/gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
      }
  )
  ```
  Re-confirm the model keys and the exact float values against the file. Ensure
  `Field` is imported in `agent/settings.py` (add the import if it is not already
  present, following the existing import style).

### 5.2 Configuration

No new env vars, config files, or feature flags. No changes to `.env.example`.
Env-var override behaviour for all four fields is unchanged.

## 6. Overleaf reference (study only — never copy)

> **No Overleaf equivalent.** This fix-pack concerns Inkstave's own Pydantic v2
> settings models and idiomatic Python defaults. Overleaf is a Node.js codebase
> and has no analogous construct. Do not consult or copy Overleaf source for this
> spec.

## 7. Acceptance criteria

Each is independently verifiable.

1. `jwt_secret_previous`, `upload_allowed_extensions`, and `allowed_upload_mime`
   in `config_groups.py`, and `agent_model_cost_table` in `agent/settings.py`,
   each use `Field(default_factory=...)`; none uses a bare mutable literal
   default.
2. Instantiating the settings models with **no** env overrides yields defaults
   **equal** to the previous values:
   - `jwt_secret_previous == []`
   - `upload_allowed_extensions == [".png", ".jpg", ".jpeg", ".gif", ".webp",
     ".pdf", ".bib", ".tex", ".cls", ".sty", ".svg", ".eps", ".csv", ".txt"]`
   - `allowed_upload_mime == ["image/png", "image/jpeg", "image/gif",
     "image/webp", "image/svg+xml", "application/pdf", "text/plain",
     "application/x-bibtex", "text/x-bibtex"]`
   - `agent_model_cost_table == {"openai/gpt-4o-mini": {"input": 0.00015,
     "output": 0.0006}}`
   (Re-confirm exact values against the source before asserting.)
3. Two independently constructed settings instances receive **non-aliased**
   mutable defaults: mutating one instance's list/dict does not affect the other,
   and the two objects are not the same identity (`is not`).
4. Env-var overrides for these fields still parse **identically** to before
   (`NoDecode` / custom decoders unchanged): a CSV/JSON override of
   `JWT_SECRET_PREVIOUS`, `UPLOAD_ALLOWED_EXTENSIONS`, `ALLOWED_UPLOAD_MIME`, and
   `AGENT_MODEL_COST_TABLE` produces the same parsed result it did prior to the
   change.
5. The `Annotated[..., NoDecode]` annotations and field decoders/validators on
   the three list fields are unchanged.
6. All existing config/settings unit and integration tests stay green.
7. The full test suite is green and runs in **< 2 minutes** (`just test-timed`).

## 8. Test plan

> Keep the combined suite under 2 minutes. These are pure in-memory model tests;
> no DB/Redis/network. The 2-minute budget is **unaffected** by this pack.

- **Stay green:** All existing settings/config tests (the suites that construct
  `Settings` / `AgentSettings` and exercise env-var parsing) must continue to
  pass unchanged.
- **New / updated unit tests** (add under `backend/tests/unit/`, e.g.
  `test_settings_mutable_defaults_98.py`):
  - **Default values preserved:** assert each of the four fields equals its prior
    default value (the exact lists/dict in §7.2).
  - **Independence (non-aliasing):** build two independent settings instances;
    assert their mutable defaults are distinct objects (`a.field is not
    b.field`); append to / mutate one and assert the other is unchanged. (This
    formalises that Pydantic deep-copies the factory output — documenting, not
    fixing, current behaviour.)
  - **Env override still parses:** with the relevant env var set, assert each
    field parses to the same value it produced before the change (reuse the
    existing parsing-test pattern / `NoDecode` decoder expectations).
- **Performance/budget note:** All tests are pure model construction (no I/O), so
  they add negligible time. Confirm with `just test-timed` (xdist).

## 9. Definition of Done

- [ ] All four fields in §5.1 use `Field(default_factory=...)` with byte-for-byte
      identical defaults.
- [ ] `Annotated[..., NoDecode]`, decoders, and env-var parsing unchanged.
- [ ] All acceptance criteria in §7 pass.
- [ ] New/updated unit tests in §8 written and green (defaults preserved,
      non-aliasing, env override parses identically).
- [ ] Full suite runs in **< 2 minutes** (`just test-timed`).
- [ ] Lint/format/type-check clean (`ruff`, type checker as configured).
- [ ] Edits limited to the files in §2 — no out-of-scope files touched; no
      `.env.example` change.
- [ ] No behaviour change; no Overleaf code copied; stack unchanged.
