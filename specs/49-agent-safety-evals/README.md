# Spec 49 — Agent Safety & Evals

**Type:** 🟢 feature  ·  **Phase:** AI writing agent  ·  **Status:** ☐ not started

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. Do this:

1. **Read the requirements.** The full, authoritative requirements for this spec
   are in [`spec.md`](spec.md) next to this file. Implement *exactly* what it
   describes — no more, no less. If something is ambiguous, prefer the simplest
   option consistent with `CLAUDE.md` and stop to ask rather than invent scope.
2. **Confirm prerequisites.** This spec depends on the **entire agent feature so
   far: specs 41–48** (graph + LLM-via-DI, tools, diff generation, streaming API,
   chat UI, diff review, context/section parsing). They must already be
   implemented and their tests passing.
3. **Study the Overleaf reference (for understanding only).** There is **NONE**:
   Overleaf has **no AI agent**, so there is nothing to reference for rate
   limits, cost budgets, prompt-injection mitigation, audit logging, or agent
   evals. Build everything from this spec. Do not copy Overleaf source code.
4. **Implement** the rate limits, token/cost budgets, prompt-injection
   mitigations, audit logging, and the deterministic eval suite described in
   `spec.md` (backend, integrated into the existing agent run path).
5. **Write the tests** listed in the spec's Test plan (all mocked: FakeLLM /
   recorded fixtures; fast).
6. **Verify.** Run the full test suite. It must pass and the whole suite must
   stay under the 2-minute budget. Then check every Acceptance criterion and
   Definition-of-Done item.
7. **Record decisions.** If you made an architectural decision, add a short note
   under `docs/`.

When all Definition-of-Done items pass, this spec is complete. Move to spec 50.

## One-line goal

The agent becomes safe to run in production: per-user/project rate limits and
token/cost budgets (env-configurable), prompt-injection mitigations so untrusted
document content can't override system instructions, audit logging of agent
actions, and a deterministic eval suite proving the agent locates sections,
proposes valid diffs, and never auto-applies.

## Do NOT (scope guard)

- Do not add new agent capabilities, tools, or UI — this spec hardens and tests
  what 41–48 already built.
- Do not change the diff format (43), the streaming protocol (44), or the
  apply-to-document flow (47) except to enforce limits/logging around them.
- Do not call a real LLM or external network in any test; everything is mocked.
- Do not copy Overleaf code (there is none for the agent).
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
