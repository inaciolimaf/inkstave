# Spec 46 — Agent Chat UI

**Type:** 🟢 feature  ·  **Phase:** AI writing agent  ·  **Status:** ☐ not started

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. Do this:

1. **Read the requirements.** The full, authoritative requirements for this spec
   are in [`spec.md`](spec.md) next to this file. Implement *exactly* what it
   describes — no more, no less. If something is ambiguous, prefer the simplest
   option consistent with `CLAUDE.md` and stop to ask rather than invent scope.
2. **Confirm prerequisites.** This spec depends on: **44** (agent API &
   streaming protocol: chat sessions, ARQ orchestration, the SSE/WS event
   stream) and **18** (CodeMirror editor UI shell the chat panel docks beside).
   They must already be implemented and their tests passing.
3. **Study the Overleaf reference (for understanding only).** There is **none**:
   Overleaf has **no AI agent**, so there is no chat panel to reference. All
   streaming-UI plumbing consumes Inkstave's own spec-44 protocol. Write
   everything independently. Do not copy Overleaf source code.
4. **Implement** the frontend chat panel described in `spec.md` (frontend-only;
   it consumes the existing spec-44 streaming endpoints).
5. **Write the tests** listed in the spec's Test plan (Vitest + React Testing
   Library units against deterministic mock event streams; one minimal
   Playwright e2e against a FakeLLM-backed backend).
6. **Verify.** Run the full test suite. It must pass and the whole suite must
   stay under the 2-minute budget. Then check every Acceptance criterion and
   Definition-of-Done item.
7. **Record decisions.** If you made an architectural decision, add a short note
   under `docs/`.

When all Definition-of-Done items pass, this spec is complete. Move to spec 47.

## One-line goal

A user opens an in-editor AI chat panel, types an instruction, and watches the
agent stream its reasoning, tool calls and assistant tokens in real time — with
stop/cancel, per-session history, clear errors, and an entry point into diff
review when the agent proposes edits.

## Do NOT (scope guard)

- Do not build the diff viewer or apply-to-document logic — that is spec 47.
  When a diff is proposed, only surface an entry point (a card/button) that hands
  the proposal id off to spec 47's review surface.
- Do not build the LaTeX section parser / context builder — that is spec 48.
- Do not build rate limits, cost budgets, audit logging or the eval suite — that
  is spec 49.
- Do not change the spec-44 streaming protocol or backend; consume it as-is.
- Do not copy Overleaf source code (there is no agent reference anyway).
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
- Do not hand-roll panel/scroll/markdown CSS; prefer shadcn/ui components.
