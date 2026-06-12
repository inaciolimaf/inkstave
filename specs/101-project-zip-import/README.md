# Spec 101 — Project Import from .zip

**Type:** 🟢 feature  ·  **Phase:** Projects & file management  ·  **Status:** ☐ not started

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. Do this:

1. **Read the requirements.** The full, authoritative requirements for this spec
   are in [`spec.md`](spec.md) next to this file. Implement *exactly* what it
   describes — no more, no less. If something is ambiguous, prefer the simplest
   option consistent with `CLAUDE.md` and stop to ask rather than invent scope.
2. **Confirm prerequisites.** This spec depends on: **11** (project model/CRUD),
   **12** (file-tree model + `SafePath`), **13** (document content), **14**
   (binary file storage), **16** (projects dashboard UI), **22** (async ARQ
   compile jobs — the job/status pattern this spec mirrors), and the spec-52
   upload-hardening helpers. They must already be implemented and their tests
   passing.
3. **Study the Overleaf reference (for understanding only).** Read the paths in
   the "Overleaf reference" section of `spec.md` inside the cloned repo at
   `../overleaf/`. **Do not copy or translate any Overleaf code** — it is AGPLv3
   and Inkstave is MIT. Learn the approach (zip-slip checks, uncompressed-size
   bounding, root-doc detection), then write your own independent implementation.
4. **Implement** the backend (upload endpoint, ARQ unpack job, tree
   reconstruction service, import-status model/route, env vars) and frontend
   (an "Import project (.zip)" action on the dashboard with upload progress and
   async-job wait) described in `spec.md`.
5. **Write the tests** listed in the spec's Test plan (unit / integration / e2e).
   Unzip work must be exercised on **tiny in-memory zips only** in the fast tier;
   no large/real archives in the suite.
6. **Verify.** Run the full test suite. It must pass and the whole suite must
   stay under the 2-minute budget. Then check every Acceptance criterion and
   Definition-of-Done item.
7. **Record decisions.** If you made an architectural decision (e.g. the
   import-status reporting channel, the binary/text split rule), add a short note
   under `docs/`.

When all Definition-of-Done items pass, this spec is complete. Move to spec 102.

## One-line goal

A user can upload a `.zip` exported from another LaTeX platform and Inkstave
unpacks it into a **brand-new** project — folders, documents, and binary files
reconstructed, with the main `.tex` detected as the root doc — safely (zip-slip
and zip-bomb proof) and without blocking the request.

## Do NOT (scope guard)

- Do not merge an uploaded archive into an existing project. Import **always**
  creates a new project.
- Do not implement `.tar`/`.tar.gz`/`.git` import, Overleaf-account sync, or
  re-export. Zip in, new project out — nothing else.
- Do not unzip synchronously in the request handler, and do not run a real heavy
  unzip in the fast test tier.
- Do not copy Overleaf source code.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
