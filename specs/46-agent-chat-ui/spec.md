# Spec 46 — Agent Chat UI (requirements)

## 1. Summary

This spec delivers the in-editor AI chat panel: a docked side panel in the
project editor where the user types natural-language instructions (e.g.
"rewrite the introduction to be more concise"), and sees the agent's response
stream live — assistant tokens, visible tool-call / tool-result steps (the agent
searching and reading the project), and proposed-diff cards that link into diff
review (spec 47). It is a pure frontend consumer of the spec-44 streaming
protocol. It adds stop/cancel, per-session message history, and explicit error
states. It does **not** render diffs, apply edits, parse LaTeX, or enforce
limits — those are specs 47, 48 and 49.

## 2. Context & dependencies

- **Depends on:**
  - spec **44** — agent API & streaming. Provides the chat-session REST
    endpoints and the streaming transport (SSE or WS) plus the canonical event
    envelope this UI renders. All event names/shapes below are the spec-44
    contract as consumed by this UI; if spec 44 names them differently, adopt
    spec 44's names and keep the rendering behaviour described here.
  - spec **18** — CodeMirror editor UI. Provides the editor route shell and
    layout into which this panel docks, plus the active-project / active-file
    context the chat panel reads to pass `project_id` (and optional
    `active_file_path`) when starting a run.
- **Unlocks:**
  - spec **47** — diff review UI (consumes the proposed-diff entry points this
    panel surfaces).
  - spec **49** — surfaces rate-limit / budget / safety errors that this panel
    must already be able to display as error states.
- **Affected areas:** frontend (`frontend/`), docs.

## 3. Goals

- A collapsible **Agent** side panel inside the editor route, toggled from the
  editor toolbar, that persists its open/closed state per browser.
- A **composer** (multiline input + send) that submits an instruction, starting
  or continuing an agent run via spec-44 endpoints.
- **Live streaming render** of the spec-44 event stream: assistant tokens
  appended incrementally; tool-call and tool-result steps shown as collapsible
  "activity" rows; a thinking/working indicator while the run is active.
- **Stop / cancel** control that aborts the in-flight run via spec 44 and leaves
  the partial transcript intact and clearly marked as cancelled.
- **Per-session message history**: messages render in order; switching the
  active session loads its prior transcript from spec 44; a "New chat" control
  starts a fresh session.
- **Proposed-diff entry points**: when the stream emits a diff-proposal event,
  render a card with file name(s) and a "Review changes" button that opens spec
  47's review surface for that proposal id. (This spec only opens the entry
  point; it never renders the diff body or applies anything.)
- **Clear error states** for transport errors, server errors, run failures, and
  spec-49 limit/budget rejections, each with a retry affordance where sensible.
- Fully keyboard-operable and screen-reader-labelled.

## 4. Non-goals (explicitly out of scope)

- The diff viewer, hunk accept/reject, file preview, and apply-to-document
  (CRDT write) — **spec 47**.
- LaTeX structure parsing / project context building — **spec 48**.
- Rate limits, token/cost budgets, prompt-injection mitigation, audit logging,
  evals — **spec 49** (this UI only *displays* limit errors it receives).
- Any change to the agent graph, tools, diff generation, or the streaming
  protocol/backend (specs 41–44).
- Multi-tab/multi-device live sync of an in-progress run (a run is owned by the
  tab that started it; other tabs may load completed transcripts via history).

## 5. Detailed requirements

> This is a **frontend-only** spec. No new tables, migrations, or backend
> endpoints. All server interaction goes through the spec-44 client.

### 5.1 Data model (frontend state only)

No database changes. Define TypeScript types mirroring the spec-44 contract.
Treat these as the shapes this UI must render; align field names with spec 44
where they differ.

```ts
type ChatRole = "user" | "assistant";

interface ChatSession {
  id: string;
  projectId: string;
  title: string | null;        // server- or first-message-derived
  createdAt: string;
  updatedAt: string;
}

// A rendered transcript item. Tool activity and diff proposals are interleaved
// with messages in arrival order.
type TranscriptItem =
  | { kind: "message"; id: string; role: ChatRole; text: string;
      status: "streaming" | "complete" | "cancelled" | "error" }
  | { kind: "tool"; id: string; name: string; args: unknown;
      result?: unknown; status: "running" | "ok" | "error";
      errorText?: string }
  | { kind: "diff-proposal"; id: string; proposalId: string;
      files: { path: string; hunkCount: number }[] }
  | { kind: "error"; id: string; code: string; message: string;
      retryable: boolean };

interface AgentRunState {
  sessionId: string;
  runId: string | null;
  phase: "idle" | "starting" | "streaming" | "stopping"
       | "done" | "error" | "cancelled";
  items: TranscriptItem[];
  error?: { code: string; message: string; retryable: boolean };
}
```

### 5.2 Backend / API (consumed, not built)

Use the spec-44 client. The endpoints used by this UI (adopt spec 44's exact
paths/verbs; the list below is the *usage contract*):

- **List sessions** for the active project — to populate the session switcher
  and "New chat" default. `GET` project chat sessions.
- **Create session** — when the user starts a new chat. `POST` create session.
- **Load transcript** for a session — when a session is opened, to render prior
  history. `GET` session messages/events.
- **Start run** — submit a user instruction into a session and open the stream.
  `POST` run start (body includes the instruction text, `project_id`, optional
  `active_file_path`); response provides a `run_id` and the stream handle
  (SSE/WS) per spec 44.
- **Stop run** — cancel an in-flight run. `POST` run cancel with `run_id`.

The UI must not assume any endpoint behaviour beyond spec 44; if spec 44 merges
"create session" and "start run", follow spec 44 and keep this UI's observable
behaviour identical.

### 5.3 Streaming event handling

The UI subscribes to the spec-44 stream and reduces events into
`AgentRunState`. Handle (at minimum) these event types from the spec-44
envelope — match spec 44's names; the semantics below are mandatory:

| Event (spec-44) | UI handling |
| --- | --- |
| run/session started | set `phase="streaming"`, store `runId`, show working indicator |
| assistant token / delta | append text to the current `message` item (create one if none open); keep autoscroll pinned to bottom unless the user scrolled up |
| assistant message complete | mark current message `status="complete"` |
| tool call start | push a `tool` item `status="running"` with `name` + `args` (collapsed by default) |
| tool result | match by tool id, set `result` and `status="ok"`/`"error"` |
| diff proposal | push a `diff-proposal` item with `proposalId` + `files[]` |
| error | push an `error` item; set `phase="error"`; populate `AgentRunState.error` |
| run finished / done | set `phase="done"`; hide working indicator |
| cancelled / aborted | mark any open streaming message `status="cancelled"`; set `phase="cancelled"` |

Rules:
- **Idempotent reducer**: events are keyed by their ids; re-applying a delivered
  event (e.g. on reconnect replay if spec 44 supports it) must not duplicate
  items. If spec 44 has no replay, a dropped stream becomes a transport error.
- **Unknown event types** are ignored (forward-compatible), not fatal.
- **Ordering**: items render in arrival order; tokens only append to the
  currently-open assistant message.

### 5.4 Frontend / UI

Route: the existing editor route from spec 18 (e.g. `/projects/:projectId`).
This spec adds a panel; it does not add a route.

Components (prefer shadcn/ui primitives — `Sheet`/resizable panel, `Button`,
`Textarea`, `ScrollArea`, `Collapsible`, `Tooltip`, `Alert`, `Card`,
`Skeleton`, `DropdownMenu`):

- **`AgentPanel`** — the dockable container. Resizable/collapsible; open/closed
  state persisted to `localStorage` keyed by project. Header shows the session
  title, a session switcher (`DropdownMenu` listing sessions + "New chat"), and
  a close button.
- **`AgentTranscript`** — scrollable list rendering `TranscriptItem[]` via the
  sub-components below; autoscrolls to bottom while streaming unless the user has
  scrolled up (then show a "Jump to latest" affordance).
- **`MessageBubble`** — renders user/assistant text. Assistant text rendered as
  sanitized markdown (code blocks monospaced); a blinking caret while
  `status==="streaming"`. Never execute or fetch from message content.
- **`ToolActivityRow`** — collapsible row: icon + human label (e.g. "Searched
  project", "Read main.tex", "Located section: Introduction"), expandable to
  show args/result JSON. Distinct visual state for `running` / `ok` / `error`.
- **`DiffProposalCard`** — shows affected file paths + total hunk count and a
  primary **"Review changes"** button. Clicking invokes a callback/route that
  spec 47 wires to its review surface, passing `proposalId`. Until spec 47
  exists, the button calls a stub handler `onReviewProposal(proposalId)` that is
  injected via props/context (so spec 47 plugs in without changing this spec).
- **`AgentComposer`** — multiline `Textarea` + send button. Enter sends,
  Shift+Enter inserts newline. Disabled (with spinner on send) while a run is
  `starting`/`streaming`. Trims empty input; ignores submits while disabled.
- **`RunControls`** — a **Stop** button visible while
  `streaming`/`starting`/`stopping`; calls stop-run, sets `phase="stopping"`,
  and resolves to `cancelled` on the cancel event (or after a short timeout →
  error state).
- **`AgentErrorState`** — `Alert` (destructive) rendering `error.code` →
  friendly message, with **Retry** when `retryable` (re-submits the last user
  instruction into the same session).

States to cover:
- **Empty session**: helper text + 2–3 example-prompt chips that prefill the
  composer.
- **Loading transcript**: `Skeleton` rows.
- **Streaming**: working indicator + Stop control + live tokens/activity.
- **Cancelled**: partial transcript preserved, "Run cancelled" marker.
- **Error**: `AgentErrorState`; composer re-enabled so the user can retry/edit.

Accessibility:
- Panel is a labelled region (`aria-label="AI agent"`); transcript is an
  `aria-live="polite"` log so new assistant text is announced (throttled).
- All controls keyboard-reachable with visible focus; Stop reachable via
  keyboard; tool rows toggle with Enter/Space.
- Composer labelled; send/stop buttons have accessible names and tooltips.

### 5.5 Configuration

- No new backend env vars. Optionally a build-time flag (e.g.
  `VITE_AGENT_ENABLED`) to hide the panel toggle when the agent feature is off;
  default on in dev. Document any flag added in `.env.example`.

## 6. Overleaf reference (study only — never copy)

- **NONE.** Overleaf has **no AI agent and no agent chat panel**, so there is
  nothing to reference for this feature. All streaming-UI behaviour derives from
  Inkstave's own spec-44 protocol. Do not import patterns from Overleaf for this
  spec.

## 7. Acceptance criteria

1. **Given** the editor route is open, **when** the user clicks the Agent toggle
   in the toolbar, **then** the `AgentPanel` opens, and its open state survives a
   page reload (persisted per project).
2. **Given** the panel is open on an empty session, **when** it renders, **then**
   example-prompt chips appear and clicking one prefills the composer.
3. **Given** the user types an instruction and presses Enter, **when** send
   fires, **then** a `user` message appears immediately, the composer disables,
   the working indicator shows, and a run is started via the spec-44 start-run
   endpoint with the active `project_id`.
4. **Given** an active run, **when** assistant token events arrive, **then** the
   assistant message text grows incrementally with a streaming caret and the
   view stays pinned to the bottom (unless the user scrolled up).
5. **Given** an active run, **when** a tool-call event then a tool-result event
   arrive, **then** a collapsible `ToolActivityRow` appears with a human label
   and transitions running→ok (or →error), expandable to show args/result.
6. **Given** an active run, **when** a diff-proposal event arrives, **then** a
   `DiffProposalCard` lists the affected files + hunk count and a "Review
   changes" button that calls `onReviewProposal(proposalId)`.
7. **Given** an active run, **when** the user clicks **Stop**, **then** the
   stop-run endpoint is called and on the cancel event any open assistant message
   is marked "cancelled", the working indicator hides, and the composer
   re-enables — with the partial transcript preserved.
8. **Given** the stream emits an error event (including a spec-49 limit/budget
   rejection surfaced as an error), **when** it is received, **then**
   `AgentErrorState` shows a friendly message and a Retry button when retryable;
   Retry re-submits the last instruction into the same session.
9. **Given** multiple sessions exist for the project, **when** the user picks a
   different session from the switcher, **then** its transcript loads (skeleton →
   rendered history) and "New chat" creates and switches to a fresh session.
10. **Given** any assistant/tool/diff content, **when** rendered, **then** it is
    sanitized (no script execution, no auto-fetch) and the panel meets the
    accessibility requirements in §5.4 (labelled live region, keyboard operation).
11. **Given** the spec-44 stream sends an unknown event type, **when** received,
    **then** it is ignored without breaking the transcript.

## 8. Test plan

> All tests combined must keep the suite under 2 minutes. No real LLM, no real
> network: drive the reducer/UI with deterministic, hand-authored event arrays.

- **Unit (Vitest + React Testing Library):**
  - The stream reducer: feed deterministic event sequences (token deltas; tool
    start/result; diff proposal; error; done; cancelled; duplicate event ids;
    unknown event) and assert the resulting `TranscriptItem[]` and `phase`.
  - `MessageBubble` renders streaming caret only while streaming; markdown is
    sanitized (inject a `<script>`/`onerror` payload and assert it is inert).
  - `AgentComposer`: Enter sends, Shift+Enter newlines, empty/whitespace blocked,
    disabled while streaming.
  - `DiffProposalCard`: "Review changes" calls `onReviewProposal` with the right
    `proposalId`.
  - `RunControls`/Stop: clicking Stop calls the (mocked) stop endpoint and the
    UI reflects cancelled state when the cancel event arrives.
  - `AgentErrorState`: retryable → Retry resubmits last instruction; non-retryable
    → no Retry button.
  - Session switcher: selecting a session loads its (mocked) transcript; "New
    chat" creates + switches.
  - Autoscroll: pinned while at bottom; "Jump to latest" appears after scrolling
    up.
- **Integration (Vitest with a mock spec-44 client / MSW):**
  - Full happy path: start run → tokens → tool steps → diff proposal → done,
    using a mocked streaming source emitting spec-44-shaped events on a timer
    that tests advance with fake timers.
- **E2E (Playwright, minimal):**
  - Against a backend wired to a **FakeLLM** that deterministically emits a
    fixed token stream + one tool step + one diff proposal: open editor, open
    Agent panel, send a prompt, assert streamed text, a tool row, and a
    "Review changes" button appear; click Stop on a longer scripted run and
    assert the cancelled marker. (One spec file; keep it short.)
- **Performance/budget note:** No real LLM/network in any tier; streaming is
  driven by fake timers or a FakeLLM script. The single Playwright file stays
  small to protect the 2-minute budget.

## 9. Definition of Done

- [ ] All requirements in §5 implemented.
- [ ] All acceptance criteria in §7 pass.
- [ ] All tests in §8 written and green.
- [ ] Full suite runs in < 2 minutes.
- [ ] Lint/format/type-check clean (ESLint + Prettier, strict TS).
- [ ] Any new build flag documented in `.env.example`; docs updated if needed.
- [ ] No Overleaf code copied (none exists for this feature).
