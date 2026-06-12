# Spec 23 — Compile Output Storage & Retrieval

**Type:** 🟢 feature  ·  **Phase:** Compilation  ·  **Status:** ☑ done

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. Do this:

1. **Read the requirements.** The full, authoritative requirements for this spec
   are in [`spec.md`](spec.md) next to this file. Implement *exactly* what it
   describes — no more, no less. If something is ambiguous, prefer the simplest
   option consistent with `CLAUDE.md` and stop to ask rather than invent scope.
2. **Confirm prerequisites.** This spec depends on: **22** (the compile ARQ job
   and `compiles` table, with the output-persistence hook left as a stub) and
   **14** (the storage abstraction). They must already be implemented and their
   tests passing.
3. **Study the Overleaf reference (for understanding only).** Read the paths in
   the "Overleaf reference" section of `spec.md` inside the cloned repo at
   `../overleaf/`. **Do not copy or translate any Overleaf code** — it is AGPLv3
   and Inkstave is MIT. Take Overleaf's output-cache/retention *concepts* only.
4. **Implement** persistence of compile outputs (PDF, `.log`, `.synctex.gz`, aux
   artifacts) via the spec-14 storage abstraction, the retention/cleanup policy,
   and the authenticated endpoints to list outputs and stream the PDF and log.
5. **Write the tests** listed in the spec's Test plan. **Use in-memory/fake
   compile results and the disk storage backend in a temp dir** — no real
   Tectonic compiles in any tier.
6. **Verify.** Run the full test suite under the 2-minute budget; check every
   Acceptance criterion and Definition-of-Done item.
7. **Record decisions.** Add an ADR if the retention policy warrants one.

When all Definition-of-Done items pass, this spec is complete. Move to spec 24.

## One-line goal

Compile outputs are persisted durably and can be listed and streamed back —
the PDF (with correct content type and HTTP range support) and the log — to
authorized users, with a retention/cleanup policy that bounds storage.

## Do NOT (scope guard)

- Do not build the PDF preview UI — that is spec 24.
- Do not parse the `.synctex.gz` or resolve synctex coordinates — that is spec 26.
- Do not parse the log into structured errors — that is spec 27.
- Do not copy Overleaf source code (CLSI is AGPLv3).
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
