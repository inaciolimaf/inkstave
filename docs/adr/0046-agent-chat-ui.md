# ADR 0046 — Agent chat UI: streaming-event reducer + SSE consumer

- **Status:** Accepted
- **Date:** 2026-06-10
- **Context spec:** 46 — Agent Chat UI

## Context

Spec 44 exposes the agent over HTTP with a live SSE event stream. Spec 46 is a
frontend-only consumer: an in-editor chat panel that posts instructions and renders
the run live (tokens, tool steps, diff-proposal cards). No backend changes.

## Decisions

### 1. A pure, idempotent reducer is the heart of the UI

`reducer.ts:applyEvent(state, event)` folds each spec-44 event into `AgentRunState`
(`items: TranscriptItem[]` + `phase` + `error`). It is a **pure function** so the
whole streaming protocol is unit-tested with hand-authored event arrays — no DOM, no
timers, no network. Key behaviours: `token` appends to the single open streaming
assistant message (creating one if none); `tool_call`/`tool_result` correlate by
`tool_call_id`; `diff_proposed` pushes a card; `done` completes the open message;
`error{code:"cancelled"}` marks it cancelled (a clean stop, not an error). Events are
**deduped by `seq`** (idempotent on replay) and **unknown types are ignored**
(forward-compatible). `historyToItems` reuses the same item types to render a loaded
transcript (stored messages + open diffs).

### 2. SSE via `EventSource`, JWT in a query param

`useAgentChat` opens the spec-44 stream with `new EventSource(runEventsUrl(...))`,
carrying the access token as `?access_token=` (EventSource can't set headers) — the
same pattern as the spec-22 compile stream. Because the backend frames events as
`event: <type>`, the hook registers one handler for each known type. On a terminal
event it `close()`s the stream (preventing EventSource auto-reconnect); a dropped
connection mid-run surfaces as a `transport` error item.

### 3. The hook owns orchestration; components are presentational

`useAgentChat` is the only stateful piece: it lists sessions (React Query), lazily
creates a session on first send, pushes the user message immediately, starts the run,
subscribes to the stream, and exposes `stop`/`retry`/`selectSession`/`newChat`. The
components (`AgentTranscript`, `MessageBubble`, `ToolActivityRow`, `DiffProposalCard`,
`AgentComposer`, `RunControls`, `AgentErrorState`) are pure renderers, each
unit-testable in isolation.

### 4. Sanitization by construction

Assistant content is rendered as **escaped React text children** (split into plain
spans + fenced `<pre><code>` blocks) — never `dangerouslySetInnerHTML`. An injected
`<script>`/`onerror` payload is therefore inert (asserted by test). No message content
is ever executed or fetched.

### 5. Diff review is a pluggable callback

`DiffProposalCard`'s "Review changes" calls an injected `onReviewProposal(proposalId)`.
Spec 47 plugs its review surface in there without touching this spec. Until then the
editor wires a toast placeholder.

### 6. Docked as a `Sheet`, open-state persisted per project

The panel is a right-side shadcn `Sheet` toggled from the editor toolbar; its
open/closed state is persisted to `localStorage` keyed by project. Behind the
`VITE_AGENT_ENABLED` build flag (default on). The panel is a labelled region
(`aria-label="AI agent"`) and the transcript an `aria-live="polite"` log.

## Consequences

- New `frontend/src/features/agent/` (types, api, reducer, `useAgentChat`, panel +
  components) and a shadcn `Textarea`. Wired into `EditorWorkspace`. One build flag.
- 21 tests: reducer (all event types, dedup, unknown, history conversion), composer/
  stop/error controls, transcript rendering + sanitization, and an `AgentPanel`
  integration test driving a mocked `EventSource` + API through the full happy path,
  Stop→cancelled, and session switching — plus one stubbed Playwright flow. No real
  LLM/network anywhere.
