# Spec 32 — Presence & awareness UI

**Type:** 🟢 feature  ·  **Phase:** Real-time collaboration  ·  **Status:** ☑ done

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. Do this:

1. **Read the requirements.** The full, authoritative requirements for this spec
   are in [`spec.md`](spec.md) next to this file. Implement *exactly* what it
   describes — no more, no less. If something is ambiguous, prefer the simplest
   option consistent with `CLAUDE.md` and stop to ask rather than invent scope.
2. **Confirm prerequisites.** This spec depends on: **31** (the `Y.Doc`, the
   `InkstaveWsProvider` with its `awareness` instance already relayed over the
   spec-29 WebSocket, the `y-codemirror.next` binding, and `useCollabDoc`). It
   assumes spec 29's WebSocket carries an awareness channel.
3. **Study the Overleaf reference (for understanding only).** Read the paths in
   the "Overleaf reference" section of `spec.md` inside the cloned repo at
   `../overleaf/`. **Do not copy or translate any Overleaf code** — it is AGPLv3
   and Inkstave is MIT. Overleaf tracks clients with its own `clientTracking`
   over Socket.IO; study only the *presence concepts* (who's online, cursor
   position broadcast, idle handling), then implement with Yjs awareness.
4. **Implement** the frontend changes described in `spec.md`: populate Yjs
   awareness with this user's identity, cursor and selection; render remote
   cursors/selections with name+color in CodeMirror via `y-codemirror.next`; show
   an "online now" avatar list; assign stable colors; throttle updates; and
   handle idle/disconnect.
5. **Write the tests** listed in the spec's Test plan (Vitest unit + a two-client
   in-process awareness test + one minimal Playwright two-context e2e).
6. **Verify.** Run the full test suite (< 2 min). Check every Acceptance
   criterion and Definition-of-Done item.
7. **Record decisions.** If you made an architectural decision (e.g. color
   assignment scheme), add a short note under `docs/`.

When all Definition-of-Done items pass, this spec is complete. Move to spec 33.

## One-line goal

Collaborators see each other's live cursors and selections (labelled with name
and a stable color) inside the editor, plus an "online now" avatar list, with
idle and disconnect states handled gracefully.

## Do NOT (scope guard)

- Do not implement sharing, invites or roles — that is spec 33.
- Do not implement permission enforcement / read-only viewers at the protocol
  level — that is spec 34. (You may read the local `readOnly` flag from spec 31
  to decide whether to broadcast a *selection*, but you do not enforce access.)
- Do not change the document-text sync from spec 31 or the backend protocol from
  spec 29 (awareness is already relayed; you only populate and render it).
- Do not copy Overleaf source code.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`):
  Yjs awareness + `y-codemirror.next` + shadcn/ui only.
