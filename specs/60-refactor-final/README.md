# Spec 60 — Final Refactor & Release-Readiness Pass

**Type:** 🔧 refactor  ·  **Phase:** Phase 7 — Hardening, packaging & docs  ·  **Status:** ☑ done

## Prompt for the implementing agent

You are implementing the **final** spec of the Inkstave system — a refactoring and
release-readiness pass, not a feature spec. Do this:

1. **Read the requirements.** The full, authoritative requirements for this spec
   are in [`spec.md`](spec.md) next to this file. This is a 🔧 refactor spec: add
   **no new features**. Scan everything built so far, evaluate each potential fix
   for risk vs. value, apply only the worthwhile ones, and keep the suite green.
2. **Confirm prerequisites.** This spec depends on **ALL** prior specs (01–59).
   They must be implemented and their tests passing before this pass begins.
3. **Study the Overleaf reference.** **None** — this is a process spec. However,
   you MUST perform an explicit **originality / license audit** confirming
   Inkstave shares no code with Overleaf (see `spec.md` §5).
4. **Execute** the release-readiness pass: bug/smell/security/doc-gap/flaky-test
   scan across all areas; verify the full suite is green and **under 2 minutes**;
   run the originality audit; produce a **release checklist** and a **final
   changelog** of applied vs. deliberately-skipped refactors.
5. **Apply** only worthwhile, low-risk fixes; keep all tests green throughout.
6. **Verify.** Run the full suite. It must pass and stay under the 2-minute
   budget. Confirm every Acceptance criterion and Definition-of-Done item.
7. **Record** the changelog, the release checklist, and the originality-audit
   result under `docs/`.

When all Definition-of-Done items pass, Inkstave is release-ready. This is the
last spec in the roadmap.

## One-line goal

The whole system gets a final quality, security, and originality pass: remaining
worthwhile fixes are applied, the suite is green and under 2 minutes, an
originality/license audit confirms independence from Overleaf, and a release
checklist + changelog are produced.

## Do NOT (scope guard)

- Do not add new features or new scope; this is a refactor/readiness pass only.
- Do not apply risky, low-value changes; record skipped items with rationale.
- Do not break the < 2-minute test budget or leave the suite red.
- Do not introduce any Overleaf code; the audit must confirm none exists.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
