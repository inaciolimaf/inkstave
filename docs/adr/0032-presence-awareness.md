# ADR 0032 — Presence: color assignment, throttling & idle/disconnect

- **Status:** Accepted
- **Date:** 2026-06-10
- **Context spec:** 32 — Presence & awareness UI

## Context

Spec 31 wired a per-document `Y.Doc` + `InkstaveWsProvider` whose `awareness`
instance is relayed over the spec-29 WebSocket. Spec 32 populates that awareness
with the local user's identity/cursor/idle and renders remote collaborators
(labelled cursors + tinted selections + an "online now" avatar list). No backend
or protocol change — awareness is opaque relay on the server.

## Decisions

### 1. Deterministic color assignment (published, not negotiated)

`colorForUser(userId)` hashes the user id (FNV-1a) into a fixed **10-color
palette** of high-contrast hues (`colors.ts`). Because every client computes it
from the same id, a user gets the **same color everywhere** — and the color is
also **published in the awareness `user` field** (`{ id, name, color,
colorLight }`), so peers agree even if a future client used a different scheme.

**Trade-off (accepted):** within a present set, two distinct users can hash to the
same color (collision). We prefer *deterministic + stable* over *guaranteed
unique* — a unique-per-room assignment would require coordination/state and would
make a user's color jump as others join/leave. Collisions are rare in the typical
small group and never break correctness.

### 2. Cursor publishing is automatic; sends are throttled

`y-codemirror.next`'s `yCollab` auto-publishes the local selection into awareness
and renders remote ones (caret bar + name label on hover via a CodeMirror
`baseTheme`, `remote-cursors.ts`; selection tint from `colorLight`). To stop rapid
caret movement flooding the channel, the provider gained an additive
`awarenessThrottleMs` option (**`CURSOR_THROTTLE_MS = 50`**, leading+trailing) that
collapses a burst of awareness sends — the awareness *state* still updates
immediately; only the *wire sends* are bounded. Identity (`user`) is set once.
This is a frontend send-rate optimisation only; the wire format is unchanged
(spec 29 untouched).

### 3. Idle handling

`usePresence` tracks activity (keydown/mouse in the editor via `markActivity`).
After **`IDLE_AFTER_MS = 60_000`** with no activity it sets an awareness
`idle: true` field (cleared on next activity); peers render idle users with a
dimmed avatar (and a faded caret is best-effort via the theme). Idle is a separate
awareness field so it doesn't perturb cursor rendering.

### 4. Disconnect cleanup — no ghost cursors

Two mechanisms remove a departed peer's caret + avatar:
- **Clean teardown:** the provider's `destroy()` now broadcasts the local
  awareness *removal* (`removeAwarenessStates` + an explicit awareness send)
  **before** detaching its listener, so peers clear immediately. `usePresence`
  also `setLocalState(null)` on unmount.
- **Abrupt disconnect:** spec-29's server already publishes an awareness "offline"
  update for a dropped connection (it learns the client's awareness id from the
  first awareness frame), so peers clear within a bounded time without any
  client-side timer. `AWARENESS_TIMEOUT_MS = 30_000` is the y-protocols
  outdated-state window (informational backstop).

### 5. Online list

`OnlineUsers` reads `awareness.getStates()` (subscribing to `change`),
**deduplicates by `user.id`** (preferring the local entry), marks the local user
"(You)", shows a shadcn `Avatar` (initials) ringed in the user's color inside a
`Tooltip` (full name + idle), and **collapses overflow beyond 5 into a "+N"**
popover. It is the screen-reader source of truth for presence (`aria-label` per
avatar); remote-cursor labels are decorative. Solo/empty renders nothing (no
crash with zero peers).

## Consequences

- New `frontend/src/features/collab/` modules: `colors.ts`, `throttle.ts`,
  `usePresence.ts`, `OnlineUsers.tsx`, `remote-cursors.ts`; a shadcn
  `Avatar` component (+ `@radix-ui/react-avatar`). The provider gained an additive
  `awarenessThrottleMs` option and a destroy-time awareness removal.
- No new env vars; tuning lives as named constants (`CURSOR_THROTTLE_MS`,
  `IDLE_AFTER_MS`, `AWARENESS_TIMEOUT_MS`) and the palette in `colors.ts`.
- Convergence/idle/throttle/overflow are in-process Vitest (mock timers, a fake
  spec-29 relay that now also relays awareness); one Playwright two-context e2e
  (`e2e/presence.spec.ts`), gated to the e2e tier (not the 2-minute budget).
- Unlocks spec 34: read-only viewers still appear in presence; whether they may
  broadcast an editing cursor is decided there (the binding already reads the
  local `readOnly` flag from spec 31).
