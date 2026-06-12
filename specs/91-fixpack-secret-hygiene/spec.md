# Spec 91 — Fix-Pack: Secret Hygiene (requirements)

## 1. Summary

This fix-pack closes a **secret-hygiene finding** raised by a code-smell audit.
The audit found a **real OpenRouter API key** (pattern `sk-or-v1-…`) sitting in
the developer's local `.env` on two lines (`openai_api_key=` and
`OPENROUTER_API_KEY=`). The `.env` file is correctly gitignored and was **never
committed**, so this is a working-tree leak risk rather than a public exposure —
but a live key in any working tree must be rotated, and the repo must gain an
automated guard so no secret (or `.env` file) can ever be committed. This pack is
**config and documentation only**: it adds a commit-time secret-scanning hook,
hardens `.gitignore` with a clarifying comment, and records a rotation ADR. It
introduces **no** behaviour change to the application and **no** Python tests.

> **Hard constraint, repeated because it matters:** the implementer must never
> write, paste, print, echo, or otherwise reproduce the real key value anywhere —
> not in the ADR, not in `.env.example`, not in a commit message, not in a test
> fixture, not in shell output. Every secret-shaped string that lands in the repo
> must be an obvious dummy/placeholder.

## 2. Files in scope

Edit **only** these files. A single new ADR may be **added** under `docs/`.

```
.pre-commit-config.yaml
.gitignore
.env.example
docs/                 (one new short ADR may be ADDED here, e.g. docs/adr/NNNN-secret-rotation.md)
```

**NOTE:** No application source, no backend/frontend code, and no test files are
in scope. If a fix appears to require any other file, stop and report.

## 3. Issues to fix

### 3.1 — Exposed OpenRouter API key in the local `.env` (major · secret hygiene)

- **File:** `docs/` (new ADR) — and, by exclusion, **not** `.env`, **not**
  `.env.example`.
- **Problem:** The audit found a **real, live** OpenRouter key (`sk-or-v1-…`) in
  the developer's local `.env`, duplicated on the `openai_api_key=` and
  `OPENROUTER_API_KEY=` lines. The file is gitignored and was never committed, so
  there is no git-history exposure to purge — but a real credential in a working
  tree is a standing leak risk (accidental paste, screen share, backup, force-add)
  and the key has been seen by tooling, so it must be treated as compromised.
- **Fix:**
  1. Add a short ADR under `docs/` (e.g. `docs/adr/NNNN-secret-rotation.md`,
     matching the numbering/format of any existing ADRs; if none exist yet, create
     `docs/adr/` and start at `0001`). The ADR must state, in plain terms:
     - the OpenRouter key previously present in a local `.env` **must be rotated**
       in the OpenRouter dashboard (revoke the old key, issue a new one);
     - the new key goes **only** into the developer's local, gitignored `.env`
       (and into deployment secret stores), **never** into the repo;
     - `.env` must **never** be committed; `.env.example` carries **placeholders
       only**;
     - going forward, the pre-commit secret-scan hook (Issue 3.2) blocks
       accidental commits of secrets and `.env` files.
  2. **Do not** write the actual key value into the ADR or anywhere else. **Do
     not** print or echo it. **Do not** add it (or any real value) to
     `.env.example` — that file keeps only the dummy placeholder
     `OPENROUTER_API_KEY=` (and the existing `openai_api_key=` placeholder) with no
     real value after the `=`.
  3. No code change and no git-history rewrite are required (the key was never
     committed). The ADR is the deliverable; rotation itself is a human action the
     ADR mandates.

### 3.2 — No automated guard against committing secrets / `.env` files (major · secret hygiene)

- **File:** `.pre-commit-config.yaml`
- **Problem:** The repo already runs `pre-commit` (ruff + the standard
  `pre-commit-hooks` set) but has **no** guard that blocks committing
  secret-looking strings or a real `.env` file. Nothing stops a developer from
  staging `.env` or pasting a key into a tracked file.
- **Fix:** Add a secret-scanning guard to `.pre-commit-config.yaml`. Choose
  **one** of the following, and configure it concretely (pin any external repo to a
  concrete release tag, matching the existing pinned-rev convention):
  - **Preferred — a well-known scanner.** Add the `gitleaks` pre-commit mirror
    (`repo: https://github.com/gitleaks/gitleaks`, pinned `rev`, `hooks: - id:
    gitleaks`) **or** `detect-secrets`
    (`repo: https://github.com/Yelp/detect-secrets`, pinned `rev`, `hooks: - id:
    detect-secrets`, with a committed `.secrets.baseline` if the hook requires
    one — note that a baseline file is then an implicit additional artifact, so
    prefer `gitleaks` if you want to avoid adding a baseline). The scanner must run
    on the staged diff at commit time.
  - **Acceptable — a dependency-free local hook.** If you want to avoid pulling a
    new external scanner, add a `repo: local` hook using `pygrep` that rejects
    commits whose **staged content** matches secret patterns, plus a hook that
    rejects staging any `.env` file other than `.env.example`. Concretely:
    - a `pygrep`-language hook with an entry regex matching at least
      `sk-or-v1-[A-Za-z0-9]+` and `sk-[A-Za-z0-9]{20,}` (OpenRouter and generic
      OpenAI-style keys), `language: pygrep`, `name: block-secret-tokens`,
      failing the commit when matched, scoped to text files;
    - a hook that blocks committing `.env`-style files: either reuse the existing
      `.gitignore` belt (Issue 3.3) **plus** a `repo: local` hook (e.g.
      `language: fail`) wired with `files: '(^|/)\.env(\..+)?$'` and
      `exclude: '(^|/)\.env\.example$'` so that staging any `.env`/`*.env`
      (but not `.env.example`) fails with a clear message.
  - Whichever option is chosen, **describe the exact hook block you added** in the
    commit/PR notes, keep the file `check-yaml`-clean and consistent with the
    existing two-space-indent style, and ensure `pre-commit run --all-files`
    passes on the current clean tree (the tree contains no real secret and no
    tracked `.env`, so a correctly-scoped hook must pass).

### 3.3 — `.gitignore` belt-and-suspenders for `.env` files (nit · secret hygiene)

- **File:** `.gitignore`
- **Problem:** `.gitignore` already ignores `.env` and `*.env` while re-including
  `!.env.example` (the rules are present and correct). The risk is that a future
  edit silently weakens them, and there is no inline note explaining why the
  ordering (`!.env.example` after `*.env`) matters.
- **Fix:** **Do not weaken or reorder** the existing rules. Verify the three lines
  are intact:
  ```
  .env
  *.env
  !.env.example
  ```
  Add a short clarifying comment next to them (e.g.
  `# never commit real secrets; .env.example holds placeholders only — keep the !.env.example line AFTER *.env`).
  Make no other change to this file. If, contrary to expectation, the rules are
  missing or weakened, restore them to the form above.

## 4. Acceptance criteria

Each is independently verifiable.

1. **(3.2)** `pre-commit run --all-files` passes on the current clean tree (exit 0).
2. **(3.2)** Staging a throwaway file containing a dummy secret line
   `OPENROUTER_API_KEY=sk-or-v1-TESTDUMMYTESTDUMMYTESTDUMMY` and attempting to
   commit it is **rejected** by the secret-scan hook (non-zero exit; the dummy is
   removed afterwards and never committed).
3. **(3.2)** Attempting to `git add` / commit a file named `.env` (or `local.env`)
   is **rejected** by the hook, while `.env.example` is **not** rejected.
4. **(3.1)** An ADR exists under `docs/` that mandates rotating the exposed
   OpenRouter key in the OpenRouter dashboard and states that `.env` must never be
   committed and `.env.example` holds placeholders only.
5. **(3.1)** `.env.example` still contains only **placeholder** secret values —
   `grep -nE 'sk-or-v1-[A-Za-z0-9]+' .env.example` returns nothing, and the
   `OPENROUTER_API_KEY=` / `openai_api_key=` lines have no real value after `=`.
6. **(3.1)** The real key value appears **nowhere** in the repository tree or
   git-tracked history added by this pack:
   `git grep -nE 'sk-or-v1-[A-Za-z0-9]{20,}'` over tracked files returns no real
   key (only the obvious `TESTDUMMY`-style placeholders in this spec / hook docs,
   if any, are acceptable).
7. **(3.3)** `.gitignore` still contains `.env`, `*.env`, and `!.env.example`
   (in that order) with a clarifying comment, and the rules are not weakened.
8. The full test suite is unaffected and still runs in **< 2 minutes** (this pack
   adds no runtime tests).

## 5. Test plan

> This pack is **config + docs only** — there are **no** Python/Vitest/Playwright
> tests to add, and no application behaviour to exercise.

- **Hook self-check:** run `pre-commit run --all-files` — it must pass on the
  clean tree (criterion 1).
- **Manual hook-trigger check (positive rejection):** create a throwaway file
  containing the dummy line
  `OPENROUTER_API_KEY=sk-or-v1-TESTDUMMYTESTDUMMYTESTDUMMY`, `git add` it, and
  attempt a commit; confirm the secret-scan hook **fails** the commit. Then create
  a throwaway `local.env` and confirm the `.env`-blocking hook **fails** it, while
  a `.env.example` edit passes. Delete the throwaway files afterwards — none of
  them, and no real secret, may be committed.
- **No real secret in the manual check:** the trigger file uses the obvious
  `TESTDUMMY` placeholder, never the real key.
- **Performance/budget note:** no new runtime tests are introduced, so the
  combined suite stays well under the 2-minute budget. The pre-commit hooks run
  only at commit time / on demand and do not count toward the test suite.

## 6. Definition of Done

- [ ] All issues in §3 resolved (rotation ADR added; secret-scan + `.env`-block
      hook active; `.gitignore` comment added without weakening rules).
- [ ] All acceptance criteria in §4 pass.
- [ ] `pre-commit run --all-files` passes on the clean tree; the manual
      hook-trigger checks in §5 reject a dummy secret and a `.env` file.
- [ ] The rotation ADR exists under `docs/` and mandates key rotation.
- [ ] **No real secret** is written, printed, or committed anywhere; `.env.example`
      holds placeholders only.
- [ ] Edits limited to the files in §2 (plus the one new ADR) — no out-of-scope
      files touched.
- [ ] `.pre-commit-config.yaml` and `.gitignore` are lint/format/`check-yaml`
      clean and match existing style.
- [ ] Full suite unchanged and runs in **< 2 minutes**; no new runtime tests.
- [ ] No Overleaf code copied. (This finding has **no Overleaf equivalent** —
      Overleaf has no comparable secret-hygiene tooling in this repo to reference;
      the guard is implemented from this spec alone.)
