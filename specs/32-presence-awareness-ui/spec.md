# Spec 32 — Presence & awareness UI (requirements)

## 1. Summary

Building on the live text sync from spec 31, this spec adds *presence*: each
collaborator's identity, cursor and selection are published through Yjs awareness
and rendered in every other client's editor (labelled cursor + tinted selection),
and an "online now" avatar list shows who is currently in the document. It
assigns each user a stable color, throttles awareness updates to keep traffic
sane, and handles idle and disconnect transitions.

## 2. Context & dependencies

- **Depends on:**
  - **Spec 31** — provides the per-document `Y.Doc`, the `InkstaveWsProvider`
    whose `awareness` instance is already relayed over the spec-29 WebSocket
    awareness channel, the `y-codemirror.next` binding, and the `useCollabDoc`
    hook / `CollabDocSession` (which already exposes `awareness`).
  - **Spec 29** — the WebSocket already broadcasts awareness update messages to a
    document room (relay only; no per-field semantics on the server).
  - **Spec 09 / user profile** — source of the current user's display name (and
    avatar/initials), obtained from the existing auth/profile layer.
- **Unlocks:** spec 34 (read-only viewers still appear in presence but may not be
  allowed to broadcast a text-editing cursor — enforcement decided there).
- **Affected areas:** frontend (editor extensions, collab module, UI components),
  docs. No backend or DB changes.

## 3. Goals

- Populate the local awareness state with a `user` field:
  `{ id, name, color }` and a `cursor` field carrying the local selection
  (anchor/head) so `y-codemirror.next` can render remote selections.
- Render remote collaborators in the editor:
  - a colored caret at each remote user's cursor position,
  - a tinted range for each remote user's selection,
  - a name label/tooltip on the caret (the user's display name).
  Use `y-codemirror.next`'s built-in remote-cursor rendering driven by the
  awareness `user`/`cursor` fields; style with the assigned color.
- Show an **"online now"** list: a horizontal stack of avatars (initials or
  profile image) for every user currently present in the document, with a
  tooltip of the full name; overflow collapses to a "+N" avatar.
- **Color assignment:** each present user gets a stable, high-contrast color
  derived deterministically (so the same user keeps the same color across all
  clients for a session); colors are visually distinct within a typical small
  group.
- **Throttle** cursor/selection awareness updates (e.g. ~50 ms) so rapid caret
  movement does not flood the channel; identity (`user`) is set once.
- **Idle handling:** after a configurable idle period with no edits/cursor
  movement, mark the user idle (dim their avatar; keep their cursor but faded).
- **Disconnect handling:** when a client disconnects, its awareness entry is
  removed (Yjs awareness timeout / `removeAwarenessStates`) so its cursor and
  avatar disappear for everyone else within a short, bounded time.

## 4. Non-goals (explicitly out of scope)

- Sharing, invites, roles, collaborator management — **spec 33**.
- Access-control enforcement (who may join, viewer read-only at protocol level) —
  **spec 34**.
- Document-text sync, providers, reconnect — owned by **spec 31** (consumed here).
- A separate "who has access" list (that is the sharing UI in spec 33); this
  spec's list is strictly *who is online in this document right now*.
- Following/jumping to a collaborator's cursor ("follow mode"). Out of scope.

## 5. Detailed requirements

### 5.1 Data model

No DB changes. Awareness state shape (the contract every client publishes):

```ts
interface AwarenessUser {
  id: string          // stable user id (from auth)
  name: string        // display name from profile
  color: string       // hex, assigned deterministically (see §5.3)
}
// y-codemirror.next reads `user` + `cursor`; we set:
awareness.setLocalStateField('user', { id, name, color })
// `cursor` (anchor/head) is set automatically by the y-codemirror.next collab
// extension when configured with this awareness instance.
```

`color` is part of the published state so all peers render the same user in the
same color without coordination.

### 5.2 Backend / API

None. Awareness travels over the spec-29 awareness channel already wired by spec
31. No new endpoints, no server logic. (Server treats awareness as opaque relay.)

### 5.3 Frontend / UI

**Color assignment (`frontend/src/features/collab/colors.ts`):**

- A fixed palette of N (≈ 8–12) distinct, accessible colors.
- `colorForUser(userId: string): string` — deterministic hash of the user id
  into the palette so a given user maps to the same color on every client. On a
  collision within the currently-present set, the assignment is still acceptable
  (deterministic > unique); document this trade-off. Color is computed locally
  from the id but also *published* in awareness so all clients agree.

**Awareness population:**

- On entering a document (in `useCollabDoc` consumer or a dedicated
  `usePresence(session)` hook), call
  `awareness.setLocalStateField('user', { id, name, color })` once, using the
  current user's id/name from the auth/profile layer.
- Configure the `y-codemirror.next` collab extension (already added in spec 31)
  with this `awareness` so it auto-publishes the local `cursor` and renders
  remote ones. Ensure remote selection/caret rendering is enabled.
- Throttle: rely on `y-codemirror.next`'s update cadence; if it publishes on
  every selection change, wrap/configure a throttle (~50 ms, trailing) so bursts
  collapse. Identity field is set once and not re-sent per keystroke.

**Editor styling (`frontend/src/features/collab/remote-cursors.css` or a CM theme):**

- Remote caret: a 2px colored bar using the peer's `color`; a small name label on
  hover/always-visible-briefly. Selections: the same color at ~20–25% opacity.
- Local user's own cursor uses the normal editor caret (not a remote style).

**"Online now" component (`OnlineUsers.tsx`):**

- Reads awareness states (subscribe to the awareness `change` event) and renders
  a deduplicated list of present users (by `user.id`), excluding/visibly marking
  the local user ("You").
- Each avatar: shadcn/ui `Avatar` with the user's image or initials, ring/border
  in the user's color, wrapped in a `Tooltip` showing the full name and an
  idle indicator if idle. Overflow beyond ~5 collapses into a `+N` avatar with a
  popover list.
- Placed in the editor toolbar/header (next to the spec-31 connection badge).
- Empty/solo state: shows just the local user (or nothing if you choose to hide
  self) — must not crash with zero remote peers.

**Idle handling (`usePresence`):**

- Track last activity (keypress, selection change). After `IDLE_AFTER_MS`
  (default 60 s) with no activity, set an awareness field `idle: true`; clear it
  on next activity. Idle peers render with dimmed avatar and faded cursor.

**Disconnect handling:**

- When the provider disconnects, Yjs awareness should time out the local entry
  for peers (configure the awareness timeout, default 30 s, or proactively
  `awareness.setLocalState(null)` / `removeAwarenessStates` on clean teardown).
- On the *viewing* side, removed states must clear the corresponding remote
  cursor and avatar promptly. Verify no "ghost" cursors linger after a peer
  leaves.

**Accessibility:**

- Avatars are buttons/links with accessible names ("`<name>` — online" / "idle").
- Remote cursor labels are decorative but the online list is the screen-reader
  source of truth for presence (`aria-label` per avatar).

### 5.4 Real-time / jobs / external integrations

- Awareness updates flow over the spec-29 awareness channel via the spec-31
  provider. No new wire messages; this spec only sets and reads awareness fields.
- Throttle constant `CURSOR_THROTTLE_MS` (≈ 50) and `IDLE_AFTER_MS` (≈ 60000) and
  awareness `AWARENESS_TIMEOUT_MS` (≈ 30000) are named frontend constants.

### 5.5 Configuration

- No new env vars. Tuning constants live in the collab module.
- The color palette lives in `colors.ts`.

## 6. Overleaf reference (study only — never copy)

> Overleaf uses Socket.IO `clientTracking` and its own remote-presence rendering,
> not Yjs awareness. Study only the *presence concepts*; implement with awareness.

- `services/real-time/app/js/ConnectedUsersManager.js` — how Overleaf tracks
  which users are connected to a project and their cursor data, including idle
  expiry. Learn the *concepts* (presence set, cursor broadcast, TTL); Yjs
  awareness provides these primitives directly.
- `services/real-time/app/js/WebsocketController.js` — where cursor/position
  updates are received and rebroadcast (`updateClientPosition`-style flows).
  Inkstave does this implicitly via the awareness relay; study for behaviour
  expectations (throttling, leave cleanup).
- `services/web/frontend/js/features/source-editor/extensions/cursor-highlights.ts`
  — how remote cursor/selection *decorations* are rendered as CodeMirror layers.
  Inkstave uses `y-codemirror.next`'s remote-cursor rendering instead; study only
  to understand the decoration/layer approach and label placement.
- `services/web/frontend/js/features/source-editor/extensions/cursor-position.ts`
  — local cursor position tracking. For Inkstave this is handled by the binding.

There is no Overleaf equivalent of "Yjs awareness state map"; that primitive is
provided by `y-protocols/awareness`.

## 7. Acceptance criteria

1. **Given** two clients in the same document, **when** client A moves its
   cursor, **then** client B sees a colored caret labelled with A's name at A's
   position within a short, throttled delay.
2. **Given** client A makes a selection, **then** client B sees that range tinted
   in A's color.
3. **Given** the same user id on any two clients, **then** that user is rendered
   in the **same color** on both (color is deterministic and published).
4. **Given** several collaborators online, **then** the "online now" list shows
   one avatar per present user (deduplicated by id), each with the user's name in
   a tooltip and a colored ring matching their cursor color; the local user is
   shown as "You" or excluded per design.
5. **Given** more present users than the avatar limit, **then** the overflow
   collapses into a "+N" avatar whose popover lists the remaining names.
6. **Given** a user is inactive beyond the idle threshold, **then** their avatar
   dims and their cursor fades on other clients; activity clears the idle state.
7. **Given** a client disconnects (closes tab / loses connection), **then** within
   the bounded awareness timeout its caret, selection and avatar disappear for
   everyone else — no ghost cursors remain.
8. **Given** rapid cursor movement, **then** awareness updates are throttled (not
   one message per pixel/selection event), verified by counting emitted updates
   over a burst.
9. **Given** a solo user (no peers), **then** the editor and online list render
   without error and show no remote cursors.

## 8. Test plan

> Keep the full suite under 2 minutes. The convergence/awareness tests use two
> in-process Yjs `Awareness` instances wired through a fake relay; exactly **one**
> minimal Playwright two-context e2e.

- **Unit (Vitest):**
  - `colorForUser` determinism: same id → same color; spread across the palette.
  - `OnlineUsers` rendering: dedup by id, "You" handling, "+N" overflow popover,
    idle dimming, empty/solo state (React Testing Library).
  - `usePresence` idle logic with mock timers: sets `idle` after threshold,
    clears on activity.
  - Throttle: simulated rapid selection changes emit a bounded number of
    awareness updates (mock timers).
- **Integration / awareness (Vitest, in-process):**
  - Two `Awareness` instances over an in-memory relay (reuse the spec-31 test
    harness): setting `user`+`cursor` on A propagates to B's state map (AC 1–3);
    removing A's state (disconnect/timeout) clears it on B (AC 7).
- **E2E (Playwright, minimal — one test):**
  - Two browser contexts in the same document: moving the cursor / making a
    selection in context A renders a labelled remote cursor and an avatar in
    context B. Single spec only, to protect the budget.
- **Performance/budget note:** all convergence and idle/throttle logic is tested
  in-process with mock timers (sub-second). Only one Playwright test runs a real
  browser. No compile or LLM calls involved.

## 9. Definition of Done

- [ ] All requirements in §5 implemented (awareness population, remote
      cursor/selection rendering, online list, colors, throttle, idle, disconnect
      cleanup).
- [ ] All acceptance criteria in §7 pass.
- [ ] All tests in §8 written and green; exactly one Playwright two-context test.
- [ ] Full suite runs in < 2 minutes.
- [ ] Lint/format/type-check clean (TS strict).
- [ ] ADR in `docs/` recording the color-assignment scheme and idle/timeout
      constants. No new env vars.
- [ ] No Overleaf code copied; only Yjs awareness + `y-codemirror.next` + shadcn/ui.
